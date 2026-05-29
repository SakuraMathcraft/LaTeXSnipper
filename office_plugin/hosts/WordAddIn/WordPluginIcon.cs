using System;
using System.Drawing;
using System.IO;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordPluginIcon
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
