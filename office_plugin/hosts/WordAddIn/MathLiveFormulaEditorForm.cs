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

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal sealed class MathLiveFormulaEditorForm : Form
{
    private const string EditorHostName = "latexsnipper.officeplugin.local";

    private readonly WebView2 _webView;
    private readonly JavaScriptSerializer _serializer = new JavaScriptSerializer();
    private FormulaMetadata? _currentInitialFormula;
    private bool _currentUpdateMode;
    private bool _initializing;
    private bool _webViewReady;
    private bool _configurationPending;

    public MathLiveFormulaEditorForm()
    {
        Text = "LaTeXSnipper";
        Width = 1180;
        Height = 760;
        MinimumSize = new System.Drawing.Size(920, 560);
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;
        Icon = WordPluginIcon.Load();

        _webView = new WebView2
        {
            Dock = DockStyle.Fill,
        };
        Controls.Add(_webView);
        Load += OnLoad;
    }

    public event EventHandler<FormulaEditorAcceptedEventArgs>? FormulaAccepted;

    public event EventHandler? EditorCancelled;

    public event EventHandler<string>? EditorError;

    public void Configure(FormulaMetadata? initialFormula, bool updateMode)
    {
        _currentInitialFormula = initialFormula;
        _currentUpdateMode = updateMode;
        _configurationPending = true;
        if (_webViewReady)
        {
            _ = ApplyConfigurationAsync();
        }
    }

    private async void OnLoad(object? sender, EventArgs e)
    {
        try
        {
            await InitializeAsync().ConfigureAwait(true);
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
        string assetsRoot = ResolveAssetsRoot();
        string userDataFolder = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "LaTeXSnipper",
            "OfficePlugin",
            "WebView2");
        Directory.CreateDirectory(userDataFolder);

        CoreWebView2Environment environment = await CoreWebView2Environment.CreateAsync(null, userDataFolder).ConfigureAwait(true);
        await _webView.EnsureCoreWebView2Async(environment).ConfigureAwait(true);
        _webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = true;
        _webView.CoreWebView2.Settings.AreDevToolsEnabled = false;
        _webView.CoreWebView2.SetVirtualHostNameToFolderMapping(
            EditorHostName,
            assetsRoot,
            CoreWebView2HostResourceAccessKind.Allow);
        _webView.CoreWebView2.WebMessageReceived += OnWebMessageReceived;
        _webView.CoreWebView2.NavigationCompleted += OnNavigationCompleted;
        _webView.Source = new Uri("https://" + EditorHostName + "/editor.html");
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
            ["display"] = _currentInitialFormula?.DisplayMode != FormulaDisplayMode.Inline,
            ["mode"] = _currentUpdateMode ? "update" : "insert",
            ["locale"] = CultureInfo.CurrentUICulture.Name,
        });
        string script =
            "(function(payload){" +
            "if(window.LaTeXSnipperEditor){window.LaTeXSnipperEditor.init(payload);}" +
            "else{window.__latexSnipperPendingInit=payload;}" +
            "})(" + payload + ");";
        await _webView.CoreWebView2.ExecuteScriptAsync(script).ConfigureAwait(true);
    }

    private void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        Dictionary<string, object>? message = _serializer.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
        if (message == null || !message.TryGetValue("type", out object rawType))
        {
            return;
        }

        string type = Convert.ToString(rawType) ?? string.Empty;
        if (type == "cancel")
        {
            EditorCancelled?.Invoke(this, EventArgs.Empty);
            Hide();
            return;
        }

        if (type != "accept")
        {
            return;
        }

        string latex = message.TryGetValue("latex", out object rawLatex) ? Convert.ToString(rawLatex) ?? string.Empty : string.Empty;
        if (string.IsNullOrWhiteSpace(latex))
        {
            return;
        }

        bool display = !message.TryGetValue("display", out object rawDisplay) || Convert.ToBoolean(rawDisplay, CultureInfo.InvariantCulture);
        FormulaAccepted?.Invoke(this, new FormulaEditorAcceptedEventArgs(_currentInitialFormula, _currentUpdateMode, latex.Trim(), display));
        Hide();
    }

    private static string ResolveAssetsRoot()
    {
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string copied = Path.Combine(baseDirectory, "EditorAssets");
        if (File.Exists(Path.Combine(copied, "editor.html")))
        {
            return copied;
        }

        string? current = baseDirectory;
        for (int i = 0; i < 8 && current != null; i++)
        {
            string candidate = Path.Combine(current, "office_plugin", "hosts", "WordAddIn", "EditorAssets");
            if (File.Exists(Path.Combine(candidate, "editor.html")))
            {
                return candidate;
            }

            current = Directory.GetParent(current)?.FullName;
        }

        throw new DirectoryNotFoundException("MathLive editor assets were not found.");
    }
}
