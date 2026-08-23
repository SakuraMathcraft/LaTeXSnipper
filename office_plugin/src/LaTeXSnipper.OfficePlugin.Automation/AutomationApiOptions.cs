using System;
using System.IO;

namespace LaTeXSnipper.OfficePlugin.Automation;

public sealed class AutomationApiOptions
{
    public AutomationApiOptions(string? connectionFilePath = null)
    {
        string defaultPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".latexsnipper",
            "automation-api.json");
        ConnectionFilePath = string.IsNullOrWhiteSpace(connectionFilePath) ? defaultPath : connectionFilePath!;
    }

    public string ConnectionFilePath { get; }

    public Uri BaseUri { get; set; } = new Uri("http://127.0.0.1:28765/");

    public string Token { get; set; } = string.Empty;

    public TimeSpan RequestTimeout { get; set; } = TimeSpan.FromSeconds(15);

    public TimeSpan ScreenshotTimeout { get; set; } = TimeSpan.FromSeconds(150);
}
