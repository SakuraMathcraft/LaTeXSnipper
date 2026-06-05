using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal static class PowerPointPluginHelp
{
    private static HelpWindow? _window;

    public static void Open()
    {
        if (_window == null || _window.IsDisposed)
        {
            _window = new HelpWindow();
        }

        _window.Show();
        _window.Activate();
    }

    private sealed class HelpWindow : Form
    {
        private const string HelpHostName = "latexsnipper-powerpoint.officeplugin.local";

        private readonly WebView2 _webView;
        private bool _initializing;

        public HelpWindow()
        {
            Text = "LaTeXSnipper Help";
            Width = 1220;
            Height = 760;
            MinimumSize = new System.Drawing.Size(900, 520);
            StartPosition = FormStartPosition.CenterScreen;
            ShowInTaskbar = true;
            Icon = PowerPointPluginIcon.Load();

            _webView = new WebView2
            {
                Dock = DockStyle.Fill,
            };
            Controls.Add(_webView);
            Load += OnLoad;
            FormClosed += (_, _) =>
            {
                _window = null;
            };
        }

        private async void OnLoad(object? sender, EventArgs e)
        {
            try
            {
                await InitializeAsync().ConfigureAwait(true);
            }
            catch (Exception exc)
            {
                MessageBox.Show(this, exc.Message, "LaTeXSnipper", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Close();
            }
        }

        private async Task InitializeAsync()
        {
            if (_initializing || _webView.CoreWebView2 != null)
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
                HelpHostName,
                assetsRoot,
                CoreWebView2HostResourceAccessKind.Allow);
            string locale = Uri.EscapeDataString(System.Globalization.CultureInfo.CurrentUICulture.Name);
            string cacheKey = DateTime.UtcNow.Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture);
            _webView.Source = new Uri("https://" + HelpHostName + "/help.html?platform=powerpoint&locale=" + locale + "&_=" + cacheKey);
        }

        private static string ResolveAssetsRoot()
        {
            return InstalledAssetResolver.FindAssetRoot("help.html")
                ?? throw new DirectoryNotFoundException("Office plugin help assets were not found.");
        }
    }
}
