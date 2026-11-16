using System.Drawing;
using System.IO;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal static class PowerPointPluginIcon
{
    public static Icon? Load()
    {
        string? path = ResolveIconPath();
        return path == null ? null : new Icon(path);
    }

    private static string? ResolveIconPath()
    {
        string? installDir = InstalledAssetResolver.FindInstallDirectory();
        if (installDir != null)
        {
            string candidate = Path.Combine(installDir, "icon.ico");
            if (File.Exists(candidate)) return candidate;
        }

        return null;
    }
}
