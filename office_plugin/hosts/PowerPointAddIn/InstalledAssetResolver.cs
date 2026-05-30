using System;
using System.IO;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal static class InstalledAssetResolver
{
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
        // ClickToRun virtualized paths (Office 365 / C2R)
        @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
        @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
    };

    /// <summary>Resolves the directory containing the installed .vsto manifest via registry,
    /// bypassing AppDomain.BaseDirectory which may point to a ClickOnce cache.</summary>
    public static string? FindInstallDirectory()
    {
        foreach (var root in new[] { Registry.LocalMachine, Registry.CurrentUser })
        {
            foreach (var subPath in RegistryPaths)
            {
                string? dir = GetManifestDirectory(root, subPath);
                if (dir != null) return dir;
            }
        }

        return null;
    }

    private static string? GetManifestDirectory(RegistryKey root, string subPath)
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

        return Path.GetDirectoryName(path);
    }

    private static string? FindFromRegistry(string assetFile)
    {
        string? installDir = FindInstallDirectory();
        if (installDir != null)
        {
            string candidate = Path.Combine(installDir, "EditorAssets");
            return File.Exists(Path.Combine(candidate, assetFile)) ? candidate : null;
        }

        return null;
    }
}
