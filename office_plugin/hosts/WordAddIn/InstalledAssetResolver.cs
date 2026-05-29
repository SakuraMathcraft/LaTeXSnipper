using System;
using System.IO;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class InstalledAssetResolver
{
    private const string RegistryPath = @"Software\Microsoft\Office\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn";

    public static string? FindAssetRoot(string assetFile)
    {
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string copied = Path.Combine(baseDirectory, "EditorAssets");
        if (File.Exists(Path.Combine(copied, assetFile)))
        {
            return copied;
        }

        // Development path: walk up for office_plugin\hosts\WordAddIn\EditorAssets
        string? current = baseDirectory;
        for (int i = 0; i < 8 && current != null; i++)
        {
            string candidate = Path.Combine(current, "office_plugin", "hosts", "WordAddIn", "EditorAssets");
            if (File.Exists(Path.Combine(candidate, assetFile)))
            {
                return candidate;
            }

            current = Directory.GetParent(current)?.FullName;
        }

        // Fallback: read VSTO manifest path from registry
        return FindFromRegistry(assetFile);
    }

    private static string? FindFromRegistry(string assetFile)
    {
        using RegistryKey? key = Registry.LocalMachine.OpenSubKey(RegistryPath);
        string? manifest = key?.GetValue("Manifest") as string;
        if (string.IsNullOrWhiteSpace(manifest))
        {
            return null;
        }

        // Parse: file:///D:/path/to/Word/AddIn.vsto|vstolocal
        string path = manifest!
            .Replace("file:///", "")
            .Replace("|vstolocal", "")
            .Replace('/', '\\');

        string? dir = Path.GetDirectoryName(path);
        if (dir == null)
        {
            return null;
        }

        string candidate = Path.Combine(dir, "EditorAssets");
        return File.Exists(Path.Combine(candidate, assetFile)) ? candidate : null;
    }
}
