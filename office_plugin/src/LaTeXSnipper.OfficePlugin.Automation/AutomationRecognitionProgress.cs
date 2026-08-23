using System;
using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Automation;

public static class AutomationRecognitionProgress
{
    public static async Task<string> RunScreenshotOcrAsync(
        AutomationApiClient client,
        Action recognizing,
        CancellationToken cancellationToken)
    {
        if (client == null)
        {
            throw new ArgumentNullException(nameof(client));
        }

        Task<string> recognition = client.ScreenshotOcrAsync(cancellationToken);
        bool posted = false;
        while (!recognition.IsCompleted)
        {
            await Task.Delay(250, cancellationToken).ConfigureAwait(false);
            if (!posted)
            {
                string status = await client.RecognitionStatusAsync(cancellationToken).ConfigureAwait(false);
                if (status.IndexOf("\"running\"", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    recognizing();
                    posted = true;
                }
            }
        }

        return await recognition.ConfigureAwait(false);
    }
}
