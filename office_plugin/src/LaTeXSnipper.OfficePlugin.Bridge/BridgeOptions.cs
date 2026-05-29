using System;

namespace LaTeXSnipper.OfficePlugin.Bridge;

public sealed class BridgeOptions
{
    public BridgeOptions(Uri baseUri)
    {
        BaseUri = baseUri ?? throw new ArgumentNullException(nameof(baseUri));
    }

    public Uri BaseUri { get; set; }

    public string Token { get; set; } = string.Empty;

    public TimeSpan Timeout { get; set; } = TimeSpan.FromSeconds(15);

    public TimeSpan ScreenshotOcrHttpTimeout { get; set; } = TimeSpan.FromSeconds(330);
}
