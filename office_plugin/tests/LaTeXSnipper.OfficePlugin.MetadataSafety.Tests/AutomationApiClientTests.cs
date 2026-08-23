using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Automation;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;
using LaTeXSnipper.OfficePlugin.WordAddIn;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.MetadataSafety.Tests;

[TestClass]
public sealed class AutomationApiClientTests
{
    [TestMethod]
    public void UserFacingAutomationAndHostErrorsAreChinese()
    {
        string[] codes =
        {
            "unauthorized", "forbidden", "queue_full", "model_unavailable", "backend_unavailable",
            "backend_unsupported", "mode_unsupported", "upstream_timeout", "upstream_error", "timeout",
            "canceled", "rate_limited", "job_not_found", "job_expired", "invalid_request", "internal_error",
            "next_result_busy", "recognition_failed",
        };

        Assert.IsTrue(codes.All(code => ContainsChinese(AutomationApiUserMessages.ForErrorCode(code))));
        Assert.IsTrue(ContainsChinese(AutomationApiUserMessages.DesktopUnavailable));
        Assert.IsTrue(ContainsChinese(WordAddInText.GetExceptionMessage(new InvalidOperationException("raw error"))));
        Assert.IsTrue(ContainsChinese(PowerPointAddInText.GetExceptionMessage(new InvalidOperationException("raw error"))));
        Assert.AreEqual("已有中文提示。", WordAddInText.GetExceptionMessage(new InvalidOperationException("已有中文提示。")));
    }

    [TestMethod]
    public async Task ClientDiscoversConnectionAuthenticatesAndCompletesOwnedJob()
    {
        string directory = Path.Combine(Path.GetTempPath(), "latexsnipper-automation-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string connectionFile = Path.Combine(directory, "automation-api.json");
        File.WriteAllText(
            connectionFile,
            "{\"base_url\":\"http://127.0.0.1:28765\",\"api_version\":\"1\",\"pid\":1,\"token\":\"session-secret\"}");
        var handler = new RecordingHandler();
        using var http = new HttpClient(handler);
        using var client = new AutomationApiClient(new AutomationApiOptions(connectionFile), http);
        try
        {
            string config = await client.ConfigureAsync(CancellationToken.None);
            string result = await client.ScreenshotOcrAsync(CancellationToken.None);

            Assert.IsTrue(config.Contains("\"api_version\":\"1\""));
            Assert.AreEqual("x^2", AutomationRecognitionParser.ParseScreenshotOcrResponse(result));
            Assert.IsTrue(handler.Requests.All(request => request.Authorization == "Bearer session-secret"));
            CollectionAssert.AreEqual(
                new[] { "GET /api/v1/config", "POST /api/v1/recognition/jobs", "GET /api/v1/recognition/jobs/job-1" },
                handler.Requests.Select(request => request.Method + " " + request.Path).ToArray());
            RecordedRequest creation = handler.Requests.Single(request => request.Method == "POST");
            StringAssert.Contains(creation.Body, "\"type\":\"next_result\"");
            Assert.IsFalse(creation.Body.Contains("desktop_capture"));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [TestMethod]
    public async Task ClientCancelsTheOwnedScreenshotJob()
    {
        string directory = Path.Combine(Path.GetTempPath(), "latexsnipper-automation-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string connectionFile = Path.Combine(directory, "automation-api.json");
        File.WriteAllText(connectionFile, "{\"base_url\":\"http://127.0.0.1:28765\",\"token\":\"session-secret\"}");
        var handler = new PendingJobHandler();
        using var http = new HttpClient(handler);
        using var client = new AutomationApiClient(new AutomationApiOptions(connectionFile), http);
        try
        {
            Task<string> recognition = client.ScreenshotOcrAsync(CancellationToken.None);
            for (int attempt = 0; attempt < 20; attempt++)
            {
                string status = await client.RecognitionStatusAsync(CancellationToken.None);
                if (status.Contains("awaiting_result"))
                {
                    break;
                }

                await Task.Delay(10);
            }

            string canceled = await client.CancelScreenshotOcrAsync(CancellationToken.None);
            Assert.IsTrue(canceled.Contains("canceled"));
            await AssertThrowsAsync<InvalidOperationException>(async () => await recognition);
            Assert.IsTrue(handler.Requests.Any(request => request.Method == "DELETE"));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [TestMethod]
    public async Task ClientStopsPollingAtTheConfiguredScreenshotTimeout()
    {
        string directory = Path.Combine(Path.GetTempPath(), "latexsnipper-automation-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string connectionFile = Path.Combine(directory, "automation-api.json");
        File.WriteAllText(connectionFile, "{\"base_url\":\"http://127.0.0.1:28765\",\"token\":\"session-secret\"}");
        var handler = new PendingJobHandler();
        using var http = new HttpClient(handler);
        var options = new AutomationApiOptions(connectionFile)
        {
            ScreenshotTimeout = TimeSpan.FromMilliseconds(50),
        };
        using var client = new AutomationApiClient(options, http);
        try
        {
            TimeoutException error = await AssertThrowsAsync<TimeoutException>(
                async () => await client.ScreenshotOcrAsync(CancellationToken.None));
            Assert.AreEqual(AutomationApiUserMessages.ScreenshotTimeout, error.Message);
            Assert.AreEqual("{\"job\":{\"state\":\"idle\"}}", await client.RecognitionStatusAsync(CancellationToken.None));
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        public List<RecordedRequest> Requests { get; } = new List<RecordedRequest>();

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string authorization = request.Headers.TryGetValues("Authorization", out IEnumerable<string> values)
                ? values.Single()
                : string.Empty;
            string path = request.RequestUri.AbsolutePath;
            string body = request.Content == null
                ? string.Empty
                : request.Content.ReadAsStringAsync().GetAwaiter().GetResult();
            Requests.Add(new RecordedRequest(request.Method.Method, path, authorization, body));
            string json;
            if (path == "/api/v1/config")
            {
                json = "{\"api_version\":\"1\"}";
            }
            else if (request.Method == HttpMethod.Post)
            {
                json = "{\"job\":{\"id\":\"job-1\",\"state\":\"awaiting_result\",\"items\":[]}}";
            }
            else
            {
                json = "{\"job\":{\"id\":\"job-1\",\"state\":\"completed\",\"items\":[{\"index\":0,\"state\":\"completed\",\"text\":\"x^2\"}]}}";
            }

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            });
        }
    }

    private sealed class PendingJobHandler : HttpMessageHandler
    {
        public List<RecordedRequest> Requests { get; } = new List<RecordedRequest>();

        private bool _canceled;

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string path = request.RequestUri.AbsolutePath;
            Requests.Add(new RecordedRequest(request.Method.Method, path, string.Empty, string.Empty));
            if (request.Method == HttpMethod.Delete)
            {
                _canceled = true;
            }

            string state = _canceled ? "canceled" : "awaiting_result";
            string json = "{\"job\":{\"id\":\"job-1\",\"state\":\"" + state + "\",\"items\":[]}}";
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json"),
            });
        }
    }

    private static bool ContainsChinese(string value)
    {
        return value.Any(character => character >= '\u3400' && character <= '\u9fff');
    }

    private static async Task<TException> AssertThrowsAsync<TException>(Func<Task> action)
        where TException : Exception
    {
        try
        {
            await action();
        }
        catch (TException exception)
        {
            return exception;
        }

        Assert.Fail("Expected exception of type " + typeof(TException).FullName + ".");
        throw new InvalidOperationException();
    }

    private sealed class RecordedRequest
    {
        public RecordedRequest(string method, string path, string authorization, string body)
        {
            Method = method;
            Path = path;
            Authorization = authorization;
            Body = body;
        }

        public string Method { get; }

        public string Path { get; }

        public string Authorization { get; }

        public string Body { get; }
    }
}
