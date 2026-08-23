using System;
using System.Globalization;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Automation;

/// <summary>Authenticated client for the desktop Automation API.</summary>
public sealed class AutomationApiClient : IDisposable
{
    private readonly AutomationApiOptions _options;
    private readonly HttpClient _httpClient;
    private readonly bool _ownsClient;
    private readonly SemaphoreSlim _configurationLock = new SemaphoreSlim(1, 1);
    private readonly object _jobLock = new object();
    private string _activeJobId = string.Empty;

    public AutomationApiClient(AutomationApiOptions options, HttpClient? httpClient = null)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _httpClient = httpClient ?? new HttpClient();
        _httpClient.Timeout = Timeout.InfiniteTimeSpan;
        _ownsClient = httpClient == null;
    }

    public async Task<string> ConfigureAsync(CancellationToken cancellationToken)
    {
        await RefreshConfigurationAsync(cancellationToken).ConfigureAwait(false);
        return await SendAsync(HttpMethod.Get, "api/v1/config", null, cancellationToken).ConfigureAwait(false);
    }

    public async Task<string> ScreenshotOcrAsync(CancellationToken cancellationToken)
    {
        await RefreshConfigurationAsync(cancellationToken).ConfigureAwait(false);
        string payload = "{\"input\":{\"type\":\"next_result\"},\"timeout\":"
            + ((int)_options.ScreenshotTimeout.TotalSeconds).ToString(CultureInfo.InvariantCulture) + "}";
        string created = await SendAsync(HttpMethod.Post, "api/v1/recognition/jobs", payload, cancellationToken).ConfigureAwait(false);
        string jobId = ExtractJsonString(created, "id");
        if (string.IsNullOrWhiteSpace(jobId))
        {
            throw new InvalidOperationException(AutomationApiUserMessages.InvalidResponse);
        }

        lock (_jobLock)
        {
            _activeJobId = jobId;
        }

        DateTime deadline = DateTime.UtcNow + _options.ScreenshotTimeout;
        try
        {
            while (DateTime.UtcNow < deadline)
            {
                cancellationToken.ThrowIfCancellationRequested();
                string status = await GetJobAsync(jobId, cancellationToken).ConfigureAwait(false);
                string state = ExtractJsonString(status, "state");
                if (string.Equals(state, "completed", StringComparison.OrdinalIgnoreCase))
                {
                    return status;
                }

                if (string.Equals(state, "failed", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(state, "canceled", StringComparison.OrdinalIgnoreCase))
                {
                    string code = ExtractJsonString(status, "code");
                    throw new InvalidOperationException(AutomationApiUserMessages.ForErrorCode(code));
                }

                await Task.Delay(250, cancellationToken).ConfigureAwait(false);
            }

            throw new TimeoutException(AutomationApiUserMessages.ScreenshotTimeout);
        }
        finally
        {
            if (!cancellationToken.IsCancellationRequested)
            {
                lock (_jobLock)
                {
                    if (string.Equals(_activeJobId, jobId, StringComparison.Ordinal))
                    {
                        _activeJobId = string.Empty;
                    }
                }
            }
        }
    }

    public async Task<string> RecognitionStatusAsync(CancellationToken cancellationToken)
    {
        string jobId;
        lock (_jobLock)
        {
            jobId = _activeJobId;
        }

        return string.IsNullOrWhiteSpace(jobId)
            ? "{\"job\":{\"state\":\"idle\"}}"
            : await GetJobAsync(jobId, cancellationToken).ConfigureAwait(false);
    }

    public async Task<string> CancelScreenshotOcrAsync(CancellationToken cancellationToken)
    {
        string jobId;
        lock (_jobLock)
        {
            jobId = _activeJobId;
        }

        if (string.IsNullOrWhiteSpace(jobId))
        {
            return "{\"job\":{\"state\":\"idle\"}}";
        }

        string result = await SendAsync(HttpMethod.Delete, "api/v1/recognition/jobs/" + Uri.EscapeDataString(jobId), null, cancellationToken).ConfigureAwait(false);
        lock (_jobLock)
        {
            if (string.Equals(_activeJobId, jobId, StringComparison.Ordinal))
            {
                _activeJobId = string.Empty;
            }
        }

        return result;
    }

    public void Dispose()
    {
        _configurationLock.Dispose();
        if (_ownsClient)
        {
            _httpClient.Dispose();
        }
    }

    private Task<string> GetJobAsync(string jobId, CancellationToken cancellationToken)
    {
        return SendAsync(HttpMethod.Get, "api/v1/recognition/jobs/" + Uri.EscapeDataString(jobId), null, cancellationToken);
    }

    private async Task RefreshConfigurationAsync(CancellationToken cancellationToken)
    {
        await _configurationLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            AutomationApiConfiguration configuration = AutomationApiConfiguration.Read(_options.ConnectionFilePath);
            if (string.IsNullOrWhiteSpace(configuration.BaseUrl) || string.IsNullOrWhiteSpace(configuration.Token))
            {
                throw new InvalidOperationException(AutomationApiUserMessages.ConnectionInfoInvalid);
            }

            _options.BaseUri = new Uri(configuration.BaseUrl.TrimEnd('/') + "/");
            _options.Token = configuration.Token;
        }
        finally
        {
            _configurationLock.Release();
        }
    }

    private async Task<string> SendAsync(HttpMethod method, string path, string? json, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(method, new Uri(_options.BaseUri, path));
        request.Headers.TryAddWithoutValidation("Authorization", "Bearer " + _options.Token);
        if (json != null)
        {
            request.Content = new StringContent(json, Encoding.UTF8, "application/json");
        }

        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(_options.RequestTimeout);
        try
        {
            using HttpResponseMessage response = await _httpClient.SendAsync(request, timeout.Token).ConfigureAwait(false);
            string body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                string code = ExtractJsonString(body, "code");
                throw new InvalidOperationException(AutomationApiUserMessages.ForErrorCode(code));
            }

            return body;
        }
        catch (HttpRequestException exc)
        {
            throw new InvalidOperationException(GetConnectionErrorMessage(), exc);
        }
        catch (TaskCanceledException exc) when (!cancellationToken.IsCancellationRequested)
        {
            throw new TimeoutException(AutomationApiUserMessages.RequestTimeout, exc);
        }
    }

    internal static string ExtractJsonString(string json, string key)
    {
        if (string.IsNullOrWhiteSpace(json) || string.IsNullOrWhiteSpace(key))
        {
            return string.Empty;
        }

        string marker = "\"" + key + "\"";
        int keyIndex = json.IndexOf(marker, StringComparison.Ordinal);
        int colonIndex = keyIndex < 0 ? -1 : json.IndexOf(':', keyIndex + marker.Length);
        int quoteIndex = colonIndex < 0 ? -1 : json.IndexOf('"', colonIndex + 1);
        if (quoteIndex < 0)
        {
            return string.Empty;
        }

        var builder = new StringBuilder();
        bool escaping = false;
        for (int index = quoteIndex + 1; index < json.Length; index++)
        {
            char value = json[index];
            if (escaping)
            {
                builder.Append(value);
                escaping = false;
            }
            else if (value == '\\')
            {
                escaping = true;
            }
            else if (value == '"')
            {
                return builder.ToString();
            }
            else
            {
                builder.Append(value);
            }
        }

        return string.Empty;
    }

    private static string GetConnectionErrorMessage()
    {
        return AutomationApiUserMessages.DesktopUnavailable;
    }
}
