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
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string copied = Path.Combine(baseDirectory, "icon.ico");
        if (File.Exists(copied))
        {
            return copied;
        }

        return null;
    }
}
