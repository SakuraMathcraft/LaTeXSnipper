using System;
using System.IO;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal static class InstalledAssetResolver
{
    private const string RegistryPath = @"Software\Microsoft\Office\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn";

    public static string? FindAssetRoot(string assetFile)
    {
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string copied = Path.Combine(baseDirectory, "EditorAssets");
        if (File.Exists(Path.Combine(copied, assetFile)))
        {
            return copied;
        }

        string? current = baseDirectory;
        for (int i = 0; i < 8 && current != null; i++)
        {
            string candidate = Path.Combine(current, "office_plugin", "hosts", "PowerPointAddIn", "EditorAssets");
            if (File.Exists(Path.Combine(candidate, assetFile)))
            {
                return candidate;
            }

            current = Directory.GetParent(current)?.FullName;
        }

        return FindFromRegistry(assetFile);
    }

    private static readonly string[] RegistryPaths =
    {
        @"Software\Microsoft\Office\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
        @"Software\Microsoft\Office\16.0\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
    };

    private static string? FindFromRegistry(string assetFile)
    {
        foreach (var root in new[] { Registry.LocalMachine, Registry.CurrentUser })
        {
            foreach (var subPath in RegistryPaths)
            {
                string? candidate = TryRegistryPath(root, subPath, assetFile);
                if (candidate != null) return candidate;
            }
        }

        return null;
    }

    private static string? TryRegistryPath(RegistryKey root, string subPath, string assetFile)
    {
        using RegistryKey? key = root.OpenSubKey(subPath);
        string? manifest = key?.GetValue("Manifest") as string;
        if (string.IsNullOrWhiteSpace(manifest))
        {
            return null;
        }

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
