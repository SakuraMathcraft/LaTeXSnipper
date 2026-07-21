#if NET48
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class WebView2MathJaxJavaScriptRuntime : IMathJaxJavaScriptRuntime, IDisposable
{
    private const string MathJaxVirtualHostName = "mathjax.latexsnipper.local";
    private static readonly TimeSpan StartupTimeout = TimeSpan.FromSeconds(15);

    private readonly string _hostName;
    private readonly Thread _uiThread;
    private readonly TaskCompletionSource<Form> _hostReady = new TaskCompletionSource<Form>();
    private readonly TaskCompletionSource<WebView2> _webViewReady = new TaskCompletionSource<WebView2>();
    private ApplicationContext? _applicationContext;
    private bool _initialized;
    private bool _disposed;

    public WebView2MathJaxJavaScriptRuntime(string hostName)
    {
        if (string.IsNullOrWhiteSpace(hostName))
        {
            throw new ArgumentException("Host name is required.", nameof(hostName));
        }

        _hostName = hostName;
        _uiThread = new Thread(RunUiThread)
        {
            IsBackground = true,
            Name = "LaTeXSnipper " + hostName + " MathJax"
        };
        _uiThread.SetApartmentState(ApartmentState.STA);
        _uiThread.Start();
    }

    public Task InitializeAsync(
        string mathJaxBundlePath,
        string configurationScript,
        string bootstrapScript,
        CancellationToken cancellationToken)
    {
        if (_initialized)
        {
            return Task.CompletedTask;
        }

        if (string.IsNullOrWhiteSpace(mathJaxBundlePath) || !File.Exists(mathJaxBundlePath))
        {
            throw new FileNotFoundException("MathJax bundle was not found.", mathJaxBundlePath);
        }

        return RunOnUiThreadAsync(async webView =>
        {
            string userDataFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "LaTeXSnipper",
                "OfficePlugin",
                _hostName,
                "MathJaxWebView2");
            CoreWebView2Environment environment = await CoreWebView2Environment.CreateAsync(null, userDataFolder).ConfigureAwait(true);
            await webView.EnsureCoreWebView2Async(environment).ConfigureAwait(true);
            webView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            webView.CoreWebView2.Settings.AreDevToolsEnabled = false;
            string mathJaxRoot = Directory.GetParent(Directory.GetParent(mathJaxBundlePath)!.FullName)!.FullName;
            webView.CoreWebView2.SetVirtualHostNameToFolderMapping(
                MathJaxVirtualHostName,
                mathJaxRoot,
                CoreWebView2HostResourceAccessKind.DenyCors);
            string bundleRelativePath = GetVirtualBundlePath(mathJaxRoot, mathJaxBundlePath);
            string html = BuildHostHtml(configurationScript, bundleRelativePath);
            await NavigateToStringAsync(webView, html).ConfigureAwait(true);
            await WaitForMathJaxStartupAsync(webView, cancellationToken).ConfigureAwait(true);
            await webView.CoreWebView2.ExecuteScriptAsync(bootstrapScript).ConfigureAwait(true);
            _initialized = true;
        }, cancellationToken);
    }

    public Task<string> EvaluateAsync(string script, CancellationToken cancellationToken)
    {
        if (!_initialized)
        {
            throw new InvalidOperationException("MathJax JavaScript runtime has not been initialized.");
        }

        return RunOnUiThreadAsync(webView => webView.CoreWebView2.ExecuteScriptAsync(script), cancellationToken);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        if (_hostReady.Task.Status == TaskStatus.RanToCompletion)
        {
            Form host = _hostReady.Task.Result;
            if (!host.IsDisposed && host.IsHandleCreated)
            {
                host.BeginInvoke(new Action(() =>
                {
                    _applicationContext?.ExitThread();
                    host.Dispose();
                }));
            }
        }
    }

    private void RunUiThread()
    {
        try
        {
            var hostForm = new HiddenWebViewHostForm();
            var webView = new WebView2
            {
                Dock = DockStyle.Fill
            };
            hostForm.Controls.Add(webView);

            // WebView2 needs real Win32 handles and an STA message loop, but the
            // renderer host must never become a user-visible top-level window.
            _ = hostForm.Handle;
            _ = webView.Handle;
            _applicationContext = new ApplicationContext();
            _hostReady.TrySetResult(hostForm);
            _webViewReady.TrySetResult(webView);
            Application.Run(_applicationContext);
        }
        catch (Exception ex)
        {
            _hostReady.TrySetException(ex);
            _webViewReady.TrySetException(ex);
        }
    }

    private async Task RunOnUiThreadAsync(Func<WebView2, Task> action, CancellationToken cancellationToken)
    {
        await RunOnUiThreadAsync(async webView =>
        {
            await action(webView).ConfigureAwait(true);
            return true;
        }, cancellationToken).ConfigureAwait(false);
    }

    private async Task<T> RunOnUiThreadAsync<T>(Func<WebView2, Task<T>> action, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Form host = await _hostReady.Task.ConfigureAwait(false);
        WebView2 webView = await _webViewReady.Task.ConfigureAwait(false);
        if (host.IsDisposed || !host.IsHandleCreated)
        {
            throw new InvalidOperationException("MathJax rendering host is unavailable.");
        }

        var completion = new TaskCompletionSource<T>();
        host.BeginInvoke(new Action(async () =>
        {
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                T result = await action(webView).ConfigureAwait(true);
                completion.TrySetResult(result);
            }
            catch (Exception ex)
            {
                completion.TrySetException(ex);
            }
        }));

        using (cancellationToken.Register(() => completion.TrySetCanceled()))
        {
            return await completion.Task.ConfigureAwait(false);
        }
    }

    private sealed class HiddenWebViewHostForm : Form
    {
        private const int WsExToolWindow = 0x00000080;
        private const int WsExAppWindow = 0x00040000;

        public HiddenWebViewHostForm()
        {
            ShowInTaskbar = false;
            FormBorderStyle = FormBorderStyle.None;
            ControlBox = false;
            Width = 1;
            Height = 1;
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams parameters = base.CreateParams;
                parameters.ExStyle |= WsExToolWindow;
                parameters.ExStyle &= ~WsExAppWindow;
                return parameters;
            }
        }

        protected override void SetVisibleCore(bool value)
        {
            base.SetVisibleCore(false);
        }
    }

    private static Task NavigateToStringAsync(WebView2 webView, string html)
    {
        var completion = new TaskCompletionSource<object?>();
        EventHandler<CoreWebView2NavigationCompletedEventArgs>? handler = null;
        handler = (sender, args) =>
        {
            webView.NavigationCompleted -= handler;
            if (args.IsSuccess)
            {
                completion.TrySetResult(null);
            }
            else
            {
                completion.TrySetException(new InvalidOperationException("WebView2 navigation failed: " + args.WebErrorStatus.ToString()));
            }
        };
        webView.NavigationCompleted += handler;
        webView.NavigateToString(html);
        return completion.Task;
    }

    private static string GetVirtualBundlePath(string mathJaxRoot, string mathJaxBundlePath)
    {
        string relativePath = mathJaxBundlePath.Substring(mathJaxRoot.Length)
            .TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
            .Replace(Path.DirectorySeparatorChar, '/');
        return "https://" + MathJaxVirtualHostName + "/" + relativePath;
    }

    private static string BuildHostHtml(string configurationScript, string bundleUri)
    {
        return "<!doctype html><html><head><meta charset=\"utf-8\"><script>"
            + configurationScript
            + "</script><script id=\"MathJax-script\" src=\""
            + bundleUri
            + "\"></script></head><body></body></html>";
    }

    private static async Task WaitForMathJaxStartupAsync(WebView2 webView, CancellationToken cancellationToken)
    {
        DateTime deadline = DateTime.UtcNow + StartupTimeout;
        while (DateTime.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            string ready = await webView.CoreWebView2.ExecuteScriptAsync(
                "Boolean(window.LaTeXSnipperMathJaxStartupReady)").ConfigureAwait(true);
            if (string.Equals(ready, "true", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            await Task.Delay(50, cancellationToken).ConfigureAwait(true);
        }

        throw new TimeoutException("MathJax startup timed out.");
    }
}
#endif
