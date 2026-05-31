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

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointStatusTaskPaneControl : UserControl, IPowerPointStatusSink, IPowerPointFormulaOptionsProvider
{
    private const string TaskPaneHostName = "latexsnipper-powerpoint.officeplugin.local";

    private readonly JavaScriptSerializer _serializer = new JavaScriptSerializer();
    private readonly WebView2 _webView;
    private string _currentLatex = PowerPointPluginController.DefaultLatex;
    private string? _savedLatex;
    private bool _webViewReady;
    private bool _initializing;
    private PowerPointStatusKind _lastStatusKind = PowerPointStatusKind.Info;
    private string _lastStatusMessage = string.Empty;
    private bool _lastBusy;
    private bool _lastOcrActive;
    private bool _lastUpdateMode;

    public PowerPointStatusTaskPaneControl()
    {
        Dock = DockStyle.Fill;
        _lastStatusMessage = PowerPointAddInText.Get("ReadyStatus");
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

    public string CurrentLatex => _currentLatex.Trim();

    public PowerPointFormulaOptions GetFormulaOptions()
    {
        return new PowerPointFormulaOptions();
    }

    public void ResetFormulaDraft()
    {
        RunOnUi(() =>
        {
            if (_savedLatex != null)
            {
                _currentLatex = _savedLatex;
                _savedLatex = null;
            }
            else
            {
                _currentLatex = PowerPointPluginController.DefaultLatex;
            }

            _lastUpdateMode = false;
            _ = ApplyStateAsync();
        });
    }

    public void Post(PowerPointStatusKind kind, string message)
    {
        RunOnUi(() =>
        {
            _lastStatusKind = kind;
            _lastStatusMessage = string.IsNullOrWhiteSpace(message) ? PowerPointAddInText.Get("ReadyStatus") : message.Trim();
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
            if (updateMode && _savedLatex == null)
            {
                _savedLatex = _currentLatex;
            }

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
            Post(PowerPointStatusKind.Error, exc.Message);
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
        }
    }

    private void ReadState(Dictionary<string, object> message)
    {
        _currentLatex = ReadString(message, "latex", _currentLatex);
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
            ["officePlugin"] = PowerPointAddInText.Get("OfficePluginLabel"),
            ["connect"] = PowerPointAddInText.Get("ConnectButton"),
            ["equation"] = PowerPointAddInText.Get("EquationLabel"),
            ["insert"] = PowerPointAddInText.Get("EditorInsert"),
            ["screenshotOcr"] = PowerPointAddInText.Get("ScreenshotOcrButton"),
            ["cancelOcr"] = PowerPointAddInText.Get("CancelOcrButton"),
        };
    }

    private static string ReadString(Dictionary<string, object> message, string key, string fallback)
    {
        return message.TryGetValue(key, out object value) ? Convert.ToString(value) ?? fallback : fallback;
    }

    private static string ResolveAssetsRoot()
    {
        return InstalledAssetResolver.FindAssetRoot("taskpane.html")
            ?? throw new DirectoryNotFoundException("Task pane assets were not found.");
    }
}
