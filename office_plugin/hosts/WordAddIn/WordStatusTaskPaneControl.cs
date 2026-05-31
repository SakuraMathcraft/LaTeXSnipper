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

public sealed class WordStatusTaskPaneControl : UserControl, IWordStatusSink, IWordFormulaOptionsProvider
{
    private const string TaskPaneHostName = "latexsnipper-word.officeplugin.local";
    private const string DefaultLatex = "e^{i\\pi}+1=0";

    private readonly JavaScriptSerializer _serializer = new JavaScriptSerializer();
    private readonly WebView2 _webView;
    private string _currentLatex = DefaultLatex;
    private bool _displayMode = true;
    private bool _autoNumber;
    private string _manualNumber = string.Empty;
    private FormulaDraftState? _savedDraftState;
    private bool _webViewReady;
    private bool _initializing;
    private WordStatusKind _lastStatusKind = WordStatusKind.Info;
    private string _lastStatusMessage = string.Empty;
    private bool _lastBusy;
    private bool _lastOcrActive;
    private bool _lastUpdateMode;

    private sealed class FormulaDraftState
    {
        public FormulaDraftState(string latex, bool displayMode, bool autoNumber, string manualNumber)
        {
            Latex = latex;
            DisplayMode = displayMode;
            AutoNumber = autoNumber;
            ManualNumber = manualNumber;
        }

        public string Latex { get; }

        public bool DisplayMode { get; }

        public bool AutoNumber { get; }

        public string ManualNumber { get; }
    }

    public WordStatusTaskPaneControl()
    {
        Dock = DockStyle.Fill;
        _lastStatusMessage = WordAddInText.Get("ReadyStatus");
        _webView = new WebView2
        {
            Dock = DockStyle.Fill,
        };
        Controls.Add(_webView);
        Load += OnLoad;
    }

    public event EventHandler? ConnectRequested;

    public event EventHandler? InsertRequested;

    public event EventHandler? ScreenshotOcrRequested;

    public event EventHandler? RenumberRequested;

    public string CurrentLatex => _currentLatex.Trim();

    public WordFormulaOptions GetFormulaOptions()
    {
        NumberingMode numberingMode = _autoNumber
            ? NumberingMode.Automatic
            : string.IsNullOrWhiteSpace(_manualNumber) ? NumberingMode.None : NumberingMode.Manual;
        bool display = _displayMode || numberingMode != NumberingMode.None;
        return new WordFormulaOptions(display, numberingMode, _manualNumber.Trim());
    }

    public void ApplyFormulaMetadata(FormulaMetadata metadata, bool updateMode)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        RunOnUi(() =>
        {
            if (updateMode && _savedDraftState == null)
            {
                _savedDraftState = new FormulaDraftState(_currentLatex, _displayMode, _autoNumber, _manualNumber);
            }

            _currentLatex = metadata.Latex;
            _displayMode = metadata.DisplayMode == FormulaDisplayMode.Display || metadata.NumberingMode != NumberingMode.None;
            _autoNumber = metadata.NumberingMode == NumberingMode.Automatic;
            _manualNumber = metadata.NumberingMode == NumberingMode.Manual ? metadata.NumberText : string.Empty;
            _lastUpdateMode = updateMode;
            _ = ApplyStateAsync();
        });
    }

    public void ResetFormulaDraft()
    {
        RunOnUi(() =>
        {
            FormulaDraftState? saved = _savedDraftState;
            _currentLatex = saved?.Latex ?? DefaultLatex;
            _displayMode = saved?.DisplayMode ?? true;
            _autoNumber = saved?.AutoNumber ?? false;
            _manualNumber = saved?.ManualNumber ?? string.Empty;
            _savedDraftState = null;
            _lastUpdateMode = false;
            _ = ApplyStateAsync();
        });
    }

    public void Post(WordStatusKind kind, string message)
    {
        RunOnUi(() =>
        {
            _lastStatusKind = kind;
            _lastStatusMessage = string.IsNullOrWhiteSpace(message) ? WordAddInText.Get("ReadyStatus") : message.Trim();
            _ = ApplyStatusAsync();
        });
    }

    public void SetBusy(bool busy)
    {
        RunOnUi(() =>
        {
            _lastBusy = busy;
            _ = ApplyStatusAsync();
        });
    }

    public void SetOcrActive(bool active)
    {
        RunOnUi(() =>
        {
            _lastOcrActive = active;
            _ = ApplyStatusAsync();
        });
    }

    public void SetCurrentFormula(string latex, bool updateMode)
    {
        RunOnUi(() =>
        {
            _currentLatex = latex ?? string.Empty;
            _lastUpdateMode = updateMode;
            _ = ApplyStateAsync();
        });
    }

    private async void OnLoad(object? sender, EventArgs e)
    {
        try
        {
            await InitializeAsync().ConfigureAwait(true);
        }
        catch (Exception exc)
        {
            Post(WordStatusKind.Error, exc.Message);
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
        _webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
        _webView.CoreWebView2.Settings.AreDevToolsEnabled = false;
        _webView.CoreWebView2.SetVirtualHostNameToFolderMapping(
            TaskPaneHostName,
            assetsRoot,
            CoreWebView2HostResourceAccessKind.Allow);
        _webView.CoreWebView2.WebMessageReceived += OnWebMessageReceived;
        _webView.CoreWebView2.NavigationCompleted += OnNavigationCompleted;
        _webView.Source = new Uri("https://" + TaskPaneHostName + "/taskpane.html?_=" + DateTime.UtcNow.Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private async void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        _webViewReady = e.IsSuccess;
        if (!_webViewReady)
        {
            return;
        }

        await ApplyStateAsync().ConfigureAwait(true);
        await ApplyStatusAsync().ConfigureAwait(true);
    }

    private void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        Dictionary<string, object>? message = _serializer.Deserialize<Dictionary<string, object>>(e.WebMessageAsJson);
        if (message == null || !message.TryGetValue("type", out object rawType))
        {
            return;
        }

        string type = Convert.ToString(rawType) ?? string.Empty;
        if (type == "state")
        {
            ReadState(message);
            return;
        }

        switch (type)
        {
            case "connect":
                ConnectRequested?.Invoke(this, EventArgs.Empty);
                break;
            case "insert":
                ReadState(message);
                InsertRequested?.Invoke(this, EventArgs.Empty);
                break;
            case "ocr":
                ScreenshotOcrRequested?.Invoke(this, EventArgs.Empty);
                break;
            case "renumber":
                RenumberRequested?.Invoke(this, EventArgs.Empty);
                break;
        }
    }

    private void ReadState(Dictionary<string, object> message)
    {
        _currentLatex = ReadString(message, "latex", _currentLatex);
        _displayMode = ReadBool(message, "display", _displayMode);
        _autoNumber = ReadBool(message, "autoNumber", _autoNumber);
        _manualNumber = ReadString(message, "manualNumber", _manualNumber);
    }

    private async Task ApplyStateAsync()
    {
        if (!_webViewReady)
        {
            return;
        }

        var payload = new Dictionary<string, object>
        {
            ["type"] = "state",
            ["latex"] = _currentLatex,
            ["display"] = _displayMode,
            ["autoNumber"] = _autoNumber,
            ["manualNumber"] = _manualNumber,
            ["updateMode"] = _lastUpdateMode,
            ["locale"] = CultureInfo.CurrentUICulture.Name,
            ["strings"] = CreateStrings(),
        };
        await ExecuteApplyAsync(payload).ConfigureAwait(true);
    }

    private async Task ApplyStatusAsync()
    {
        if (!_webViewReady)
        {
            return;
        }

        var payload = new Dictionary<string, object>
        {
            ["type"] = "status",
            ["kind"] = _lastStatusKind.ToString().ToLowerInvariant(),
            ["message"] = _lastStatusMessage,
            ["busy"] = _lastBusy,
            ["ocrActive"] = _lastOcrActive,
        };
        await ExecuteApplyAsync(payload).ConfigureAwait(true);
    }

    private Task ExecuteApplyAsync(Dictionary<string, object> payload)
    {
        string json = _serializer.Serialize(payload);
        string script =
            "(function(payload){" +
            "if(window.LaTeXSnipperTaskPane){window.LaTeXSnipperTaskPane.apply(payload);}" +
            "else{window.__latexSnipperTaskPanePending=window.__latexSnipperTaskPanePending||[];window.__latexSnipperTaskPanePending.push(payload);}" +
            "})(" + json + ");";
        return _webView.CoreWebView2.ExecuteScriptAsync(script);
    }

    private void RunOnUi(Action action)
    {
        if (InvokeRequired)
        {
            BeginInvoke(action);
            return;
        }

        action();
    }

    private static Dictionary<string, object> CreateStrings()
    {
        return new Dictionary<string, object>
        {
            ["officePlugin"] = WordAddInText.Get("OfficePluginLabel"),
            ["connect"] = WordAddInText.Get("ConnectButton"),
            ["equation"] = WordAddInText.Get("EquationLabel"),
            ["latex"] = "LaTeX",
            ["display"] = WordAddInText.Get("DisplayOption"),
            ["autoNumber"] = WordAddInText.Get("AutoNumberOption"),
            ["manualNumber"] = WordAddInText.Get("ManualNumberPlaceholder"),
            ["screenshotOcr"] = WordAddInText.Get("ScreenshotOcrButton"),
            ["cancelOcr"] = WordAddInText.Get("CancelOcrButton"),
            ["insert"] = WordAddInText.Get("EditorInsert"),
            ["numbering"] = WordAddInText.Get("NumberingGroup"),
            ["renumber"] = WordAddInText.Get("RenumberButton"),
        };
    }

    private static string ReadString(Dictionary<string, object> message, string key, string fallback)
    {
        return message.TryGetValue(key, out object value) ? Convert.ToString(value) ?? fallback : fallback;
    }

    private static bool ReadBool(Dictionary<string, object> message, string key, bool fallback)
    {
        if (!message.TryGetValue(key, out object value))
        {
            return fallback;
        }

        if (value is bool boolValue)
        {
            return boolValue;
        }

        return bool.TryParse(Convert.ToString(value), out bool parsed) ? parsed : fallback;
    }

    private static string ResolveAssetsRoot()
    {
        return InstalledAssetResolver.FindAssetRoot("taskpane.html")
            ?? throw new DirectoryNotFoundException("Task pane assets were not found.");
    }
}
