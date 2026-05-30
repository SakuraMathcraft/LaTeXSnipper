using System;
using System.IO;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class InstalledAssetResolver
{
    public static string? FindAssetRoot(string assetFile)
    {
        // 1. Try BaseDirectory (works in dev and some install scenarios)
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string copied = Path.Combine(baseDirectory, "EditorAssets");
        if (File.Exists(Path.Combine(copied, assetFile)))
        {
            return copied;
        }

        // 2. Dev path: walk up for office_plugin/hosts/WordAddIn/EditorAssets
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

        // 3. Registry fallback: parse Manifest value to find EditorAssets next to .vsto
        string? installDir = FindInstallDirectory();
        if (installDir != null)
        {
            string candidate = Path.Combine(installDir, "EditorAssets");
            return File.Exists(Path.Combine(candidate, assetFile)) ? candidate : null;
        }

        return null;
    }

    /// <summary>Resolves the directory containing the installed .vsto manifest via registry,
    /// bypassing AppDomain.BaseDirectory which may point to a ClickOnce cache.</summary>
    public static string? FindInstallDirectory()
    {
        foreach (var root in new[] { Registry.LocalMachine, Registry.CurrentUser })
        {
            foreach (var subPath in RegistryPaths)
            {
                using RegistryKey? key = root.OpenSubKey(subPath);
                string? manifest = key?.GetValue("Manifest") as string;
                if (string.IsNullOrWhiteSpace(manifest)) continue;

                string path = manifest!
                    .Replace("file:///", "")
                    .Replace("|vstolocal", "")
                    .Replace('/', '\\');

                string? dir = Path.GetDirectoryName(path);
                if (dir != null) return dir;
            }
        }

        return null;
    }

    private static readonly string[] RegistryPaths =
    {
        @"Software\Microsoft\Office\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
        @"Software\Microsoft\Office\16.0\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
        // ClickToRun virtualized paths (Office 365 / C2R)
        @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
        @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
    };
}
