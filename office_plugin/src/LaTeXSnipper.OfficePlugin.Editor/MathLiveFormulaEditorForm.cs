#if NET48
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace LaTeXSnipper.OfficePlugin.Editor;

internal sealed class MathLiveFormulaEditorForm : Form
{
    private readonly MathLiveFormulaEditorOptions _options;
    private readonly WebView2 _webView;
    private readonly JavaScriptSerializer _serializer = new JavaScriptSerializer();
    private FormulaMetadata? _currentInitialFormula;
    private bool _currentUpdateMode;
    private bool _initializing;
    private bool _webViewReady;
    private bool _configurationPending;
    private bool _committed;
    private bool _restoredDraftForCurrentConfiguration;
    private bool _shutdownDisposing;
    private Task? _warmUpTask;

    public MathLiveFormulaEditorForm(MathLiveFormulaEditorOptions options)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
        Text = "LaTeXSnipper";
        Width = 1180;
        Height = 760;
        MinimumSize = new System.Drawing.Size(920, 560);
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;
        if (_options.Icon != null)
        {
            Icon = _options.Icon;
        }

        _webView = new WebView2
        {
            Dock = DockStyle.Fill,
        };
        Controls.Add(_webView);
        Load += OnLoad;
        Resize += OnResize;
        FormClosing += OnFormClosing;
    }

    public event Func<FormulaEditorAcceptedEventArgs, Task<FormulaEditorSubmissionResult>>? FormulaSubmitting;

    public event EventHandler? EditorCancelled;

    public event EventHandler<string>? EditorError;

    public bool CloseOnCommit { get; set; }

    public FormulaEditorAcceptedEventArgs? AcceptedFormula { get; private set; }

    public Task WarmUpAsync()
    {
        _warmUpTask ??= InitializeAsync();
        return _warmUpTask;
    }

    public void DisposeForShutdown()
    {
        _shutdownDisposing = true;
        Close();
    }

    public void Configure(FormulaMetadata? initialFormula, bool updateMode)
    {
        _currentInitialFormula = initialFormula;
        _currentUpdateMode = updateMode;
        _configurationPending = true;
        _committed = false;
        _restoredDraftForCurrentConfiguration = false;
        if (_webViewReady)
        {
            _ = ApplyConfigurationAsync();
        }
    }

    private async void OnLoad(object? sender, EventArgs e)
    {
        try
        {
            await WarmUpAsync().ConfigureAwait(true);
        }
        catch (Exception exc)
        {
            EditorError?.Invoke(this, exc.Message);
            Close();
        }
    }

    private async Task InitializeAsync()
    {
        if (_initializing || _webViewReady)
        {
            return;
        }

        _initializing = true;
        string assetsRoot = MathLiveAssetResolver.FindAssetRoot(_options, "editor.html");
        string userDataFolder = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "LaTeXSnipper",
            "OfficePlugin",
            _options.WebViewUserDataFolderName);
        Directory.CreateDirectory(userDataFolder);

        CoreWebView2Environment environment = await CoreWebView2Environment.CreateAsync(null, userDataFolder).ConfigureAwait(true);
        await _webView.EnsureCoreWebView2Async(environment).ConfigureAwait(true);
        _webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
        _webView.CoreWebView2.Settings.AreDevToolsEnabled = false;
        _webView.CoreWebView2.SetVirtualHostNameToFolderMapping(
            _options.EditorHostName,
            assetsRoot,
            CoreWebView2HostResourceAccessKind.Allow);
        _webView.CoreWebView2.WebMessageReceived += OnWebMessageReceived;
        _webView.CoreWebView2.NavigationCompleted += OnNavigationCompleted;
        _webView.Source = new Uri("https://" + _options.EditorHostName + "/editor.html");
    }

    private async void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        _webViewReady = e.IsSuccess;
        if (!_webViewReady)
        {
            EditorError?.Invoke(this, "MathLive editor failed to load.");
            return;
        }

        await ApplyConfigurationAsync().ConfigureAwait(true);
    }

    private async Task ApplyConfigurationAsync()
    {
        if (!_webViewReady || !_configurationPending)
        {
            return;
        }

        _configurationPending = false;
        string payload = _serializer.Serialize(new Dictionary<string, object>
        {
            ["type"] = "init",
            ["latex"] = _currentInitialFormula?.Latex ?? string.Empty,
            ["display"] = _options.ForceDisplayMode || _currentInitialFormula?.DisplayMode != FormulaDisplayMode.Inline,
            ["mode"] = _currentUpdateMode ? "update" : "insert",
            ["locale"] = CultureInfo.CurrentUICulture.Name,
        });
        string script =
            "(function(payload){" +
            "if(window.LaTeXSnipperEditor){window.LaTeXSnipperEditor.init(payload);}" +
            "else{window.__latexSnipperPendingInit=payload;}" +
            "})(" + payload + ");";
        await ExecuteEditorScriptAsync(script).ConfigureAwait(true);
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        try
        {
            Dictionary<string, object>? message = _serializer.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
            if (message == null || !message.TryGetValue("type", out object rawType))
            {
                return;
            }

            string type = Convert.ToString(rawType) ?? string.Empty;
            if (type == "cancel")
            {
                NotifyEditorCancelled();
                Commit(DialogResult.Cancel);
                return;
            }

            if (type != "accept")
            {
                return;
            }

            await SubmitAcceptedFormulaAsync(message).ConfigureAwait(true);
        }
        catch (Exception exc)
        {
            EditorError?.Invoke(this, exc.Message);
            await TrySetSubmittingAsync(false).ConfigureAwait(true);
        }
    }

    private async Task SubmitAcceptedFormulaAsync(Dictionary<string, object> message)
    {
        string latex = message.TryGetValue("latex", out object rawLatex) ? Convert.ToString(rawLatex) ?? string.Empty : string.Empty;
        if (string.IsNullOrWhiteSpace(latex))
        {
            return;
        }

        bool display = _options.ForceDisplayMode ||
            !message.TryGetValue("display", out object rawDisplay) ||
            Convert.ToBoolean(rawDisplay, CultureInfo.InvariantCulture);
        AcceptedFormula = new FormulaEditorAcceptedEventArgs(_currentInitialFormula, _currentUpdateMode, latex.Trim(), display);
        await SetSubmittingAsync(true).ConfigureAwait(true);
        FormulaEditorSubmissionResult result = await SubmitFormulaAsync(AcceptedFormula).ConfigureAwait(true);
        if (result.Success)
        {
            await SetSubmittingAsync(false).ConfigureAwait(true);
            Commit(DialogResult.OK);
            return;
        }

        await SetSubmittingAsync(false).ConfigureAwait(true);
        await SetStatusAsync(result.Message).ConfigureAwait(true);
    }

    private Task<FormulaEditorSubmissionResult> SubmitFormulaAsync(FormulaEditorAcceptedEventArgs accepted)
    {
        Func<FormulaEditorAcceptedEventArgs, Task<FormulaEditorSubmissionResult>>? handler = FormulaSubmitting;
        return handler == null
            ? Task.FromResult(FormulaEditorSubmissionResult.Rejected("Formula submit handler is not connected."))
            : handler(accepted);
    }

    private async Task SetSubmittingAsync(bool submitting)
    {
        if (!_webViewReady)
        {
            return;
        }

        string payload = _serializer.Serialize(submitting);
        await ExecuteEditorScriptAsync(
            "window.LaTeXSnipperEditor&&window.LaTeXSnipperEditor.setSubmitting(" + payload + ");").ConfigureAwait(true);
    }

    private async Task TrySetSubmittingAsync(bool submitting)
    {
        try
        {
            await SetSubmittingAsync(submitting).ConfigureAwait(true);
        }
        catch (Exception exc)
        {
            EditorError?.Invoke(this, exc.Message);
        }
    }

    private async Task SetStatusAsync(string message)
    {
        if (!_webViewReady || string.IsNullOrWhiteSpace(message))
        {
            return;
        }

        string payload = _serializer.Serialize(message);
        await ExecuteEditorScriptAsync(
            "window.LaTeXSnipperEditor&&window.LaTeXSnipperEditor.setStatus(" + payload + ");").ConfigureAwait(true);
    }

    private Task ExecuteEditorScriptAsync(string script)
    {
        if (InvokeRequired)
        {
            var completion = new TaskCompletionSource<object?>();
            BeginInvoke(new Action(async () =>
            {
                try
                {
                    if (_webViewReady && _webView.CoreWebView2 != null)
                    {
                        await _webView.CoreWebView2.ExecuteScriptAsync(script).ConfigureAwait(true);
                    }

                    completion.SetResult(null);
                }
                catch (Exception exc)
                {
                    completion.SetException(exc);
                }
            }));
            return completion.Task;
        }

        if (!_webViewReady || _webView.CoreWebView2 == null)
        {
            return Task.CompletedTask;
        }

        return _webView.CoreWebView2.ExecuteScriptAsync(script);
    }

    private void OnResize(object? sender, EventArgs e)
    {
        if (WindowState == FormWindowState.Minimized)
        {
            NotifyEditorCancelled();
        }
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        if (!_shutdownDisposing)
        {
            if (!_committed)
            {
                NotifyEditorCancelled();
            }

            e.Cancel = true;
            Hide();
            return;
        }

        if (!_committed)
        {
            NotifyEditorCancelled();
        }
    }

    private void NotifyEditorCancelled()
    {
        if (!_currentUpdateMode || _restoredDraftForCurrentConfiguration)
        {
            return;
        }

        _restoredDraftForCurrentConfiguration = true;
        EditorCancelled?.Invoke(this, EventArgs.Empty);
    }

    private void Commit(DialogResult result)
    {
        _committed = true;
        if (CloseOnCommit)
        {
            DialogResult = result;
            Close();
            return;
        }

        Hide();
    }
}
#endif
