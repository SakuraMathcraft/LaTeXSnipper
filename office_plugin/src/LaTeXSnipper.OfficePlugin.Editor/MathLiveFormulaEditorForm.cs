#if NET48
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
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
    private InputLanguageSnapshot? _inputLanguageBeforeActivation;
    private Task? _warmUpTask;

    private const int WmInputLangChangeRequest = 0x0050;

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, IntPtr processId);

    [DllImport("user32.dll")]
    private static extern IntPtr GetKeyboardLayout(uint idThread);

    [DllImport("user32.dll")]
    private static extern IntPtr ActivateKeyboardLayout(IntPtr hkl, uint flags);

    [DllImport("user32.dll")]
    private static extern bool PostMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

    [DllImport("imm32.dll")]
    private static extern IntPtr ImmGetContext(IntPtr hWnd);

    [DllImport("imm32.dll")]
    private static extern bool ImmReleaseContext(IntPtr hWnd, IntPtr hImc);

    [DllImport("imm32.dll")]
    private static extern bool ImmGetOpenStatus(IntPtr hImc);

    [DllImport("imm32.dll")]
    private static extern bool ImmSetOpenStatus(IntPtr hImc, bool open);

    [DllImport("imm32.dll")]
    private static extern bool ImmGetConversionStatus(IntPtr hImc, out int conversion, out int sentence);

    [DllImport("imm32.dll")]
    private static extern bool ImmSetConversionStatus(IntPtr hImc, int conversion, int sentence);

    private sealed class InputLanguageSnapshot
    {
        public InputLanguageSnapshot(
            InputLanguage inputLanguage,
            IntPtr foregroundWindow,
            IntPtr keyboardLayout,
            bool hasImeState,
            bool imeOpen,
            int imeConversion,
            int imeSentence)
        {
            InputLanguage = inputLanguage;
            ForegroundWindow = foregroundWindow;
            KeyboardLayout = keyboardLayout;
            HasImeState = hasImeState;
            ImeOpen = imeOpen;
            ImeConversion = imeConversion;
            ImeSentence = imeSentence;
        }

        public InputLanguage InputLanguage { get; }

        public IntPtr ForegroundWindow { get; }

        public IntPtr KeyboardLayout { get; }

        public bool HasImeState { get; }

        public bool ImeOpen { get; }

        public int ImeConversion { get; }

        public int ImeSentence { get; }
    }

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
        Dispose();
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

    public void CaptureInputLanguage()
    {
        IntPtr foregroundWindow = GetForegroundWindow();
        IntPtr keyboardLayout = foregroundWindow == IntPtr.Zero
            ? InputLanguage.CurrentInputLanguage.Handle
            : GetKeyboardLayout(GetWindowThreadProcessId(foregroundWindow, IntPtr.Zero));
        bool hasImeState = TryReadImeState(
            foregroundWindow,
            out bool imeOpen,
            out int imeConversion,
            out int imeSentence);
        _inputLanguageBeforeActivation = new InputLanguageSnapshot(
            InputLanguage.CurrentInputLanguage,
            foregroundWindow,
            keyboardLayout,
            hasImeState,
            imeOpen,
            imeConversion,
            imeSentence);
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
        string sharedAssetsRoot = MathLiveAssetResolver.FindSharedAssetRoot(_options, "symbol-library.js");
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
        _webView.CoreWebView2.SetVirtualHostNameToFolderMapping(
            _options.SharedEditorHostName,
            sharedAssetsRoot,
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
            ["fontStyle"] = (_currentInitialFormula?.FontStyle ?? FormulaFontStyle.TeX).ToString(),
            ["fontColor"] = _currentInitialFormula?.FontColor ?? "#000000",
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
        string fontStyleText = message.TryGetValue("fontStyle", out object rawFontStyle)
            ? Convert.ToString(rawFontStyle, CultureInfo.InvariantCulture) ?? FormulaFontStyle.TeX.ToString()
            : FormulaFontStyle.TeX.ToString();
        FormulaFontStyle fontStyle = Enum.TryParse(fontStyleText, out FormulaFontStyle parsedFontStyle)
            ? parsedFontStyle
            : FormulaFontStyle.TeX;
        AcceptedFormula = new FormulaEditorAcceptedEventArgs(_currentInitialFormula, _currentUpdateMode, latex.Trim(), display, fontStyle);
        await SetSubmittingAsync(true).ConfigureAwait(true);
        FormulaEditorSubmissionResult result = await SubmitFormulaAsync(AcceptedFormula).ConfigureAwait(true);
        if (result.Success)
        {
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
            RestoreInputLanguageAfterHide();
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

            RestoreInputLanguageAfterHide();
            return;
        }

        if (!_committed)
        {
            NotifyEditorCancelled();
        }

        RestoreInputLanguageAfterHide();
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
        DialogResult = result;
        Close();
    }

    private void RestoreInputLanguageAfterHide()
    {
        RestoreInputLanguage();
        _ = RestoreInputLanguageWhenOwnerIsForegroundAsync();
    }

    private void RestoreInputLanguage()
    {
        if (_inputLanguageBeforeActivation == null)
        {
            return;
        }

        try
        {
            InputLanguage.CurrentInputLanguage = _inputLanguageBeforeActivation.InputLanguage;
            if (_inputLanguageBeforeActivation.KeyboardLayout != IntPtr.Zero)
            {
                _ = ActivateKeyboardLayout(_inputLanguageBeforeActivation.KeyboardLayout, 0);
            }

            if (_inputLanguageBeforeActivation.ForegroundWindow != IntPtr.Zero)
            {
                _ = PostMessage(
                    _inputLanguageBeforeActivation.ForegroundWindow,
                    WmInputLangChangeRequest,
                    IntPtr.Zero,
                    _inputLanguageBeforeActivation.KeyboardLayout);
                RestoreImeState(_inputLanguageBeforeActivation);
            }
        }
        catch
        {
        }
    }

    private async Task RestoreInputLanguageWhenOwnerIsForegroundAsync()
    {
        InputLanguageSnapshot? snapshot = _inputLanguageBeforeActivation;
        if (snapshot == null)
        {
            return;
        }

        for (int attempt = 0; attempt < 20; attempt++)
        {
            if (GetForegroundWindow() == snapshot.ForegroundWindow)
            {
                RestoreInputLanguage();
                return;
            }

            await Task.Delay(50).ConfigureAwait(true);
        }

        RestoreInputLanguage();
    }

    private static bool TryReadImeState(IntPtr hWnd, out bool open, out int conversion, out int sentence)
    {
        open = false;
        conversion = 0;
        sentence = 0;
        if (hWnd == IntPtr.Zero)
        {
            return false;
        }

        IntPtr hImc = ImmGetContext(hWnd);
        if (hImc == IntPtr.Zero)
        {
            return false;
        }

        try
        {
            open = ImmGetOpenStatus(hImc);
            return ImmGetConversionStatus(hImc, out conversion, out sentence);
        }
        finally
        {
            _ = ImmReleaseContext(hWnd, hImc);
        }
    }

    private static void RestoreImeState(InputLanguageSnapshot snapshot)
    {
        if (!snapshot.HasImeState)
        {
            return;
        }

        IntPtr hImc = ImmGetContext(snapshot.ForegroundWindow);
        if (hImc == IntPtr.Zero)
        {
            return;
        }

        try
        {
            _ = ImmSetOpenStatus(hImc, snapshot.ImeOpen);
            _ = ImmSetConversionStatus(hImc, snapshot.ImeConversion, snapshot.ImeSentence);
        }
        finally
        {
            _ = ImmReleaseContext(snapshot.ForegroundWindow, hImc);
        }
    }
}
#endif
