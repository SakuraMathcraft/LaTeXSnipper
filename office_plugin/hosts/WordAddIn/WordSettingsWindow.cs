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

internal sealed class WordSettingsWindow : Form
{
    private const string SettingsHostName = "latexsnipper-word.officeplugin.local";

    private static WordSettingsWindow? _window;

    private readonly WebView2 _webView;
    private readonly JavaScriptSerializer _serializer = new JavaScriptSerializer();
    private bool _initializing;
    private bool _webViewReady;

    private WordSettingsWindow()
    {
        Text = WordAddInText.Get("SettingsTitle");
        Width = 760;
        Height = 640;
        MinimumSize = new System.Drawing.Size(620, 520);
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;
        Icon = WordPluginIcon.Load();

        _webView = new WebView2
        {
            Dock = DockStyle.Fill,
        };
        Controls.Add(_webView);
        Load += OnLoad;
        FormClosed += (_, _) => _window = null;
    }

    public static void Open()
    {
        if (_window == null || _window.IsDisposed)
        {
            _window = new WordSettingsWindow();
        }

        _window.Show();
        if (_window.WindowState == FormWindowState.Minimized)
        {
            _window.WindowState = FormWindowState.Normal;
        }

        _window.Activate();
    }

    private async void OnLoad(object? sender, EventArgs e)
    {
        try
        {
            await InitializeAsync().ConfigureAwait(true);
        }
        catch (Exception exc)
        {
            MessageBox.Show(this, exc.Message, WordAddInText.Get("ErrorTitle"), MessageBoxButtons.OK, MessageBoxIcon.Error);
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
        CoreWebView2 core = _webView.CoreWebView2 ?? throw new InvalidOperationException("WebView2 failed to initialize.");
        core.Settings.AreDefaultContextMenusEnabled = true;
        core.Settings.AreDevToolsEnabled = false;
        core.SetVirtualHostNameToFolderMapping(
            SettingsHostName,
            assetsRoot,
            CoreWebView2HostResourceAccessKind.Allow);
        core.WebMessageReceived += OnWebMessageReceived;
        core.NavigationCompleted += OnNavigationCompleted;
        _webView.Source = new Uri("https://" + SettingsHostName + "/settings.html?_=" + DateTime.UtcNow.Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private async void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        _webViewReady = e.IsSuccess;
        if (_webViewReady)
        {
            await SendSettingsAsync().ConfigureAwait(true);
        }
    }

    private async Task SendSettingsAsync()
    {
        WordPluginSettings settings = WordPluginSettings.Load();
        string payload = _serializer.Serialize(new Dictionary<string, object>
        {
            ["type"] = "init",
            ["locale"] = CultureInfo.CurrentUICulture.Name,
            ["numberPlacement"] = settings.NumberPlacement.ToString(),
            ["numberFormat"] = settings.NumberFormat.ToString(),
            ["numberEnclosure"] = settings.NumberEnclosure.ToString(),
            ["insertionBackend"] = settings.InsertionBackend.ToString(),
        });
        string script =
            "(function(payload){" +
            "if(window.LaTeXSnipperSettings){window.LaTeXSnipperSettings.init(payload);}" +
            "else{window.__latexSnipperSettingsInit=payload;}" +
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

        string type = Convert.ToString(rawType, CultureInfo.InvariantCulture) ?? string.Empty;
        if (type == "close")
        {
            Close();
            return;
        }

        if (type != "save")
        {
            return;
        }

        string placement = message.TryGetValue("numberPlacement", out object rawPlacement)
            ? Convert.ToString(rawPlacement, CultureInfo.InvariantCulture) ?? string.Empty
            : string.Empty;
        string backend = message.TryGetValue("insertionBackend", out object rawBackend)
            ? Convert.ToString(rawBackend, CultureInfo.InvariantCulture) ?? string.Empty
            : string.Empty;
        FormulaInsertionBackend insertionBackend = backend == FormulaInsertionBackend.WordOmml.ToString()
            ? FormulaInsertionBackend.WordOmml
            : FormulaInsertionBackend.Ole;
        string formatRaw = message.TryGetValue("numberFormat", out object rawFormat)
            ? Convert.ToString(rawFormat, CultureInfo.InvariantCulture) ?? string.Empty
            : string.Empty;
        string enclosureRaw = message.TryGetValue("numberEnclosure", out object rawEnclosure)
            ? Convert.ToString(rawEnclosure, CultureInfo.InvariantCulture) ?? string.Empty
            : string.Empty;
        WordNumberFormat numberFormat = Enum.TryParse(formatRaw, out WordNumberFormat parsedFormat)
            ? parsedFormat
            : WordNumberFormat.Arabic;
        WordNumberEnclosure numberEnclosure = Enum.TryParse(enclosureRaw, out WordNumberEnclosure parsedEnclosure)
            ? parsedEnclosure
            : WordNumberEnclosure.Parentheses;
        var settings = new WordPluginSettings(
            placement == "Left" ? WordNumberPlacement.Left : WordNumberPlacement.Right,
            insertionBackend,
            numberFormat,
            numberEnclosure);
        settings.Save();
        _ = SendSettingsAsync();
    }

    private static string ResolveAssetsRoot()
    {
        return InstalledAssetResolver.FindAssetRoot("settings.html")
            ?? throw new DirectoryNotFoundException("Office plugin settings assets were not found.");
    }
}
