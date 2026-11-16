using System;
using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Automation;

public static class AutomationRecognitionProgress
{
    private const int PollIntervalMilliseconds = 250;

    public static async Task<string> RunScreenshotOcrAsync(
        AutomationApiClient client,
        Action recognizing,
        CancellationToken cancellationToken)
    {
        if (client == null)
        {
            throw new ArgumentNullException(nameof(client));
        }
        if (recognizing == null)
        {
            throw new ArgumentNullException(nameof(recognizing));
        }

        Task<string> recognition = client.ScreenshotOcrAsync(cancellationToken);
        bool posted = false;
        while (!recognition.IsCompleted)
        {
            await Task.Delay(PollIntervalMilliseconds, cancellationToken).ConfigureAwait(false);
            if (recognition.IsCompleted || posted)
            {
                continue;
            }

            if (await IsRecognizingAsync(client, cancellationToken).ConfigureAwait(false))
            {
                recognizing();
                posted = true;
            }
        }

        return await recognition.ConfigureAwait(false);
    }

    private static async Task<bool> IsRecognizingAsync(
        AutomationApiClient client,
        CancellationToken cancellationToken)
    {
        try
        {
            string status = await client.RecognitionStatusAsync(cancellationToken).ConfigureAwait(false);
            return status.IndexOf("\"state\"", StringComparison.OrdinalIgnoreCase) >= 0
                && status.IndexOf("\"running\"", StringComparison.OrdinalIgnoreCase) >= 0;
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
}
