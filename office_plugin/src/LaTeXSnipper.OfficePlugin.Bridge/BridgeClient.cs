using System;
using System.Globalization;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Bridge;

/// <summary>
/// HTTP boundary for desktop screenshot recognition.
/// </summary>
public sealed class BridgeClient : IDisposable
{
    private readonly BridgeOptions _options;
    private readonly HttpClient _httpClient;
    private readonly bool _ownsClient;
    private readonly SemaphoreSlim _configurationLock = new SemaphoreSlim(1, 1);

    public BridgeClient(BridgeOptions options, HttpClient? httpClient = null)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _httpClient = httpClient ?? new HttpClient();
        _httpClient.Timeout = System.Threading.Timeout.InfiniteTimeSpan;
        _ownsClient = httpClient == null;
    }

    public Task<string> HealthAsync(CancellationToken cancellationToken)
    {
        return SendAsync(HttpMethod.Get, "health", null, cancellationToken, requiresAuthentication: false);
    }

    public Task<string> ConfigAsync(CancellationToken cancellationToken)
    {
        return SendAsync(HttpMethod.Get, "config", null, cancellationToken, requiresAuthentication: false);
    }

    public async Task<string> ConfigureAsync(CancellationToken cancellationToken)
    {
        await EnsureConfiguredAsync(cancellationToken).ConfigureAwait(false);
        return await HealthAsync(cancellationToken).ConfigureAwait(false);
    }

    public Task<string> ScreenshotOcrAsync(CancellationToken cancellationToken)
    {
        return SendAsync(
            HttpMethod.Post,
            "recognize/screenshot",
            "{\"timeout\":" + ((int)_options.ScreenshotOcrHttpTimeout.TotalSeconds - 30).ToString(System.Globalization.CultureInfo.InvariantCulture) + "}",
            cancellationToken,
            requiresAuthentication: true,
            requestTimeout: _options.ScreenshotOcrHttpTimeout,
            timeoutMessage: "Screenshot OCR timed out. Start Screenshot OCR again and complete a screenshot in LaTeXSnipper.");
    }

    public Task<string> RecognitionStatusAsync(CancellationToken cancellationToken)
    {
        return SendAsync(
            HttpMethod.Post,
            "recognition/status",
            "{}",
            cancellationToken,
            requiresAuthentication: true,
            requestTimeout: TimeSpan.FromSeconds(2));
    }

    public Task<string> CancelScreenshotOcrAsync(CancellationToken cancellationToken)
    {
        return SendAsync(
            HttpMethod.Post,
            "recognize/screenshot/cancel",
            "{}",
            cancellationToken,
            requiresAuthentication: true);
    }

    public void Dispose()
    {
        _configurationLock.Dispose();
        if (_ownsClient)
        {
            _httpClient.Dispose();
        }
    }

    private async Task<string> SendAsync(
        HttpMethod method,
        string relativePath,
        string? jsonPayload,
        CancellationToken cancellationToken,
        bool requiresAuthentication,
        TimeSpan? requestTimeout = null,
        string? timeoutMessage = null)
    {
        if (requiresAuthentication)
        {
            await EnsureConfiguredAsync(cancellationToken).ConfigureAwait(false);
        }

        using var request = new HttpRequestMessage(method, new Uri(_options.BaseUri, relativePath));
        if (requiresAuthentication)
        {
            request.Headers.TryAddWithoutValidation("Authorization", "Bearer " + _options.Token);
        }

        if (jsonPayload != null)
        {
            request.Content = new StringContent(jsonPayload, Encoding.UTF8, "application/json");
        }

        using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeoutSource.CancelAfter(requestTimeout ?? _options.Timeout);
        HttpResponseMessage response;
        try
        {
            response = await _httpClient.SendAsync(request, timeoutSource.Token).ConfigureAwait(false);
        }
        catch (HttpRequestException exc)
        {
            throw new InvalidOperationException(GetConnectionErrorMessage(), exc);
        }
        catch (TaskCanceledException exc) when (!cancellationToken.IsCancellationRequested)
        {
            throw new TimeoutException(timeoutMessage ?? "Bridge request timed out.", exc);
        }

        using (response)
        {
            string body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                throw new InvalidOperationException(CreateHttpErrorMessage(response, body));
            }

            return body;
        }
    }

    private static string CreateHttpErrorMessage(HttpResponseMessage response, string body)
    {
        string bridgeMessage = ExtractJsonString(body, "message");
        if (!string.IsNullOrWhiteSpace(bridgeMessage))
        {
            return bridgeMessage;
        }

        string reason = response.ReasonPhrase ?? string.Empty;
        return string.IsNullOrWhiteSpace(reason)
            ? "Bridge request failed with HTTP " + ((int)response.StatusCode).ToString(System.Globalization.CultureInfo.InvariantCulture) + "."
            : reason;
    }

    private static string GetConnectionErrorMessage()
    {
        return CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "zh"
            ? "无法连接到 LaTeXSnipper。请确认桌面端正在运行，并且已开启 Office 插件功能。"
            : "Unable to connect to LaTeXSnipper. Make sure the desktop client is running and the Office plugin feature is enabled.";
    }

    private static string ExtractJsonString(string json, string key)
    {
        if (string.IsNullOrWhiteSpace(json) || string.IsNullOrWhiteSpace(key))
        {
            return string.Empty;
        }

        string marker = "\"" + key + "\"";
        int keyIndex = json.IndexOf(marker, StringComparison.Ordinal);
        if (keyIndex < 0)
        {
            return string.Empty;
        }

        int colonIndex = json.IndexOf(':', keyIndex + marker.Length);
        if (colonIndex < 0)
        {
            return string.Empty;
        }

        int quoteIndex = json.IndexOf('"', colonIndex + 1);
        if (quoteIndex < 0)
        {
            return string.Empty;
        }

        var builder = new StringBuilder();
        bool escaping = false;
        for (int i = quoteIndex + 1; i < json.Length; i++)
        {
            char c = json[i];
            if (escaping)
            {
                builder.Append(c switch
                {
                    '"' => '"',
                    '\\' => '\\',
                    '/' => '/',
                    'b' => '\b',
                    'f' => '\f',
                    'n' => '\n',
                    'r' => '\r',
                    't' => '\t',
                    _ => c,
                });
                escaping = false;
                continue;
            }

            if (c == '\\')
            {
                escaping = true;
                continue;
            }

            if (c == '"')
            {
                return builder.ToString();
            }

            builder.Append(c);
        }

        return string.Empty;
    }

    private async Task EnsureConfiguredAsync(CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(_options.Token))
        {
            return;
        }

        await _configurationLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (!string.IsNullOrWhiteSpace(_options.Token))
            {
                return;
            }

            string body = await ConfigAsync(cancellationToken).ConfigureAwait(false);
            BridgeConfiguration configuration = BridgeConfiguration.FromJson(body);
            if (string.IsNullOrWhiteSpace(configuration.Token))
            {
                throw new InvalidOperationException("Bridge config did not return a session token.");
            }

            if (!string.IsNullOrWhiteSpace(configuration.BridgeUrl))
            {
                string normalized = configuration.BridgeUrl.EndsWith("/", StringComparison.Ordinal)
                    ? configuration.BridgeUrl
                    : configuration.BridgeUrl + "/";
                _options.BaseUri = new Uri(normalized);
            }

            _options.Token = configuration.Token;
        }
        finally
        {
            _configurationLock.Release();
        }
    }

}
