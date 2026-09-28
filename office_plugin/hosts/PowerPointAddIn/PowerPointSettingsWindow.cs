using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal sealed class PowerPointSettingsWindow : Form
{
    private const string SettingsHostName = "latexsnipper-powerpoint.officeplugin.local";

    private static PowerPointSettingsWindow? _window;

    private readonly WebView2 _webView;
    private readonly JavaScriptSerializer _serializer = new JavaScriptSerializer();
    private bool _initializing;
    private bool _webViewReady;

    private PowerPointSettingsWindow()
    {
        Text = PowerPointAddInText.Get("SettingsTitle");
        Width = 760;
        Height = 640;
        MinimumSize = new System.Drawing.Size(620, 520);
        StartPosition = FormStartPosition.CenterScreen;
        ShowInTaskbar = true;
        Icon = PowerPointPluginIcon.Load();

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
            _window = new PowerPointSettingsWindow();
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
            MessageBox.Show(this, PowerPointAddInText.GetExceptionMessage(exc), PowerPointAddInText.Get("ErrorTitle"), MessageBoxButtons.OK, MessageBoxIcon.Error);
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
        CoreWebView2 core = _webView.CoreWebView2 ?? throw new InvalidOperationException("WebView2 初始化失败，请确认已安装 Microsoft Edge WebView2 Runtime。");
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
        PowerPointPluginSettings settings = PowerPointPluginSettings.Load();
        string payload = _serializer.Serialize(new Dictionary<string, object>
        {
            ["type"] = "init",
            ["locale"] = CultureInfo.CurrentUICulture.Name,
            ["platform"] = "powerpoint",
            ["insertionBackend"] = settings.InsertionBackend.ToString(),
            ["formulaColor"] = settings.FormulaColor,
            ["formulaMathStyle"] = settings.FormulaMathStyle.ToString(),
            ["formulaFontSizePoints"] = settings.FormulaFontSizePoints,
            ["symbolFontId"] = settings.Typography.SymbolFontId,
            ["numberFontFamily"] = settings.Typography.NumberFontFamily ?? string.Empty,
            ["cjkFontFamily"] = settings.Typography.CjkFontFamily,
            ["symbolFonts"] = new MathJaxAssetResolver().SymbolFonts,
            ["systemFonts"] = TypographySystemFonts.List(),
            ["cjkFonts"] = TypographySystemFonts.ListCjk(),
            ["mathStyles"] = FormulaMathStyleCatalog.List(),
            ["namedSizes"] = FormulaFontSize.NamedSizes.Select(size => new { name = size.Key, points = size.Value }).ToArray(),
            ["commonPointSizes"] = FormulaFontSize.CommonPointSizes.ToArray(),
            ["followHostFontSize"] = settings.FollowHostFontSize,
        });
        string script =
            "(function(payload){" +
            "if(window.LaTeXSnipperSettings){window.LaTeXSnipperSettings.init(payload);}" +
            "else{window.__latexSnipperSettingsInit=payload;}" +
            "})(" + payload + ");";
        await _webView.CoreWebView2.ExecuteScriptAsync(script).ConfigureAwait(true);
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
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

        if (type == "importTypography" || type == "exportTypography")
        {
            await HandleTypographyFileAsync(type).ConfigureAwait(true);
            return;
        }

        if (type != "save")
        {
            return;
        }

        string backend = message.TryGetValue("insertionBackend", out object rawBackend)
            ? Convert.ToString(rawBackend, CultureInfo.InvariantCulture) ?? string.Empty
            : string.Empty;
        FormulaInsertionBackend insertionBackend = backend == FormulaInsertionBackend.PowerPointPng.ToString()
            ? FormulaInsertionBackend.PowerPointPng
            : FormulaInsertionBackend.Ole;
        string formulaColor = message.TryGetValue("formulaColor", out object rawColor)
            ? Convert.ToString(rawColor, CultureInfo.InvariantCulture) ?? "#000000"
            : "#000000";
        string fontStyleText = message.TryGetValue("formulaMathStyle", out object rawStyle)
            ? Convert.ToString(rawStyle, CultureInfo.InvariantCulture) ?? FormulaMathStyle.Automatic.ToString()
            : FormulaMathStyle.Automatic.ToString();
        FormulaMathStyle fontStyle = Enum.TryParse(fontStyleText, out FormulaMathStyle parsedStyle)
            ? parsedStyle
            : FormulaMathStyle.Automatic;
        double formulaFontSizePoints = message.TryGetValue("formulaFontSizePoints", out object rawScale) &&
            double.TryParse(
                Convert.ToString(rawScale, CultureInfo.InvariantCulture),
                NumberStyles.Float,
                CultureInfo.InvariantCulture,
                out double parsedScale)
            ? parsedScale
            : 12;
        bool followHost = message.TryGetValue("followHostFontSize", out object follow) && Convert.ToBoolean(follow);
        PowerPointPluginSettings current = PowerPointPluginSettings.Load();
        string symbolFontId = ReadString(message, "symbolFontId", current.Typography.SymbolFontId);
        if (!new MathJaxAssetResolver().SymbolFonts.Contains(symbolFontId))
            throw new FormatException("无效的数学符号字体：" + symbolFontId);
        string numberFont = ReadString(message, "numberFontFamily", string.Empty);
        var typography = new FormulaTypography(symbolFontId, numberFont.Length == 0 ? null : numberFont,
            ReadString(message, "cjkFontFamily", current.Typography.CjkFontFamily), fontStyle, formulaFontSizePoints, formulaColor);
        new PowerPointPluginSettings(insertionBackend, formulaColor, fontStyle, formulaFontSizePoints, followHost, typography).Save();
        if (!current.Typography.Equals(typography) || current.FollowHostFontSize != followHost)
            new TypographySettingsStore().Save("powerpoint", typography, followHost);
        _ = SendSettingsAsync();
    }

    private async Task HandleTypographyFileAsync(string type)
    {
        string kind = type == "importTypography" ? "import" : "export";
        string name;
        try
        {
            var store = new TypographySettingsStore();
            if (kind == "import")
            {
                using var dialog = new OpenFileDialog { Filter = "JSON preset (*.json)|*.json", CheckFileExists = true };
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                name = store.Import("powerpoint", dialog.FileName, new MathJaxAssetResolver().SymbolFonts);
                await SendSettingsAsync().ConfigureAwait(true);
            }
            else
            {
                using var dialog = new SaveFileDialog { Filter = "JSON preset (*.json)|*.json", FileName = "PowerPoint 公式设置.json" };
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                store.Export("powerpoint", dialog.FileName);
                name = Path.GetFileNameWithoutExtension(dialog.FileName);
            }
            await SendTypographyResultAsync(kind, name, null).ConfigureAwait(true);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or FormatException or ArgumentException)
        {
            await SendTypographyResultAsync(kind, string.Empty, error.Message).ConfigureAwait(true);
        }
    }

    private Task SendTypographyResultAsync(string kind, string name, string? error)
    {
        var result = new Dictionary<string, object> { ["kind"] = kind, ["name"] = name };
        if (error != null) result["error"] = error;
        return _webView.CoreWebView2.ExecuteScriptAsync(
            "window.LaTeXSnipperSettings?.presetResult(" + _serializer.Serialize(result) + ");");
    }

    private static string ReadString(Dictionary<string, object> message, string key, string fallback)
    {
        string value = message.TryGetValue(key, out object raw)
            ? Convert.ToString(raw, CultureInfo.InvariantCulture) ?? string.Empty : string.Empty;
        return string.IsNullOrWhiteSpace(value) ? fallback : value;
    }

    private static string ResolveAssetsRoot()
    {
        return InstalledAssetResolver.FindAssetRoot("settings.html")
            ?? throw new DirectoryNotFoundException("Office plugin settings assets were not found.");
    }
}
