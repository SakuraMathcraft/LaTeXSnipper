using System;
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
        // 1. Try BaseDirectory (works in dev and some install scenarios)
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string copied = Path.Combine(baseDirectory, "icon.ico");
        if (File.Exists(copied))
        {
            return copied;
        }

        // 2. Registry fallback: find install dir from Manifest value, then look for icon.ico
        string? installDir = InstalledAssetResolver.FindInstallDirectory();
        if (installDir != null)
        {
            string candidate = Path.Combine(installDir, "icon.ico");
            if (File.Exists(candidate)) return candidate;
        }

        return null;
    }
}
