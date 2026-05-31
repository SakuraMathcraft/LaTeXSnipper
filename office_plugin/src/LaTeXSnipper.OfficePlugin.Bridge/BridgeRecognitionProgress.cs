using System;
using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Bridge;

public static class BridgeRecognitionProgress
{
    private const int PollIntervalMilliseconds = 250;

    public static async Task<string> RunScreenshotOcrAsync(
        BridgeClient bridgeClient,
        Action recognizing,
        CancellationToken cancellationToken)
    {
        if (bridgeClient == null)
        {
            throw new ArgumentNullException(nameof(bridgeClient));
        }

        if (recognizing == null)
        {
            throw new ArgumentNullException(nameof(recognizing));
        }

        Task<string> recognitionTask = bridgeClient.ScreenshotOcrAsync(cancellationToken);
        bool postedRecognizing = false;
        while (!recognitionTask.IsCompleted)
        {
            await Task.Delay(PollIntervalMilliseconds, cancellationToken).ConfigureAwait(false);
            if (recognitionTask.IsCompleted || postedRecognizing)
            {
                continue;
            }

            if (await IsRecognizingAsync(bridgeClient, cancellationToken).ConfigureAwait(false))
            {
                recognizing();
                postedRecognizing = true;
            }
        }

        return await recognitionTask.ConfigureAwait(false);
    }

    private static async Task<bool> IsRecognizingAsync(BridgeClient bridgeClient, CancellationToken cancellationToken)
    {
        try
        {
            string statusJson = await bridgeClient.RecognitionStatusAsync(cancellationToken).ConfigureAwait(false);
            return ContainsJsonState(statusJson, "recognizing");
        }
        catch (InvalidOperationException)
        {
            return false;
        }
        catch (TimeoutException)
        {
            return false;
        }
    }

    private static bool ContainsJsonState(string json, string state)
    {
        if (string.IsNullOrWhiteSpace(json) || string.IsNullOrWhiteSpace(state))
        {
            return false;
        }

        return json.IndexOf("\"state\"", StringComparison.OrdinalIgnoreCase) >= 0
            && json.IndexOf("\"" + state + "\"", StringComparison.OrdinalIgnoreCase) >= 0;
    }
}
