using System.IO;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class InstalledAssetResolver
{
    public static string? FindAssetRoot(string assetFile)
    {
        string? installDir = FindInstallDirectory();
        if (installDir != null)
        {
            string candidate = Path.Combine(installDir, "EditorAssets");
            return File.Exists(Path.Combine(candidate, assetFile)) ? candidate : null;
        }

        return null;
    }

    public static string? FindInstallDirectory()
    {
        string? assemblyDirectory = Path.GetDirectoryName(typeof(InstalledAssetResolver).Assembly.Location);
        if (!string.IsNullOrWhiteSpace(assemblyDirectory))
        {
            return assemblyDirectory;
        }

        foreach (string subPath in RegistryPaths)
        {
            using RegistryKey? key = Registry.LocalMachine.OpenSubKey(subPath);
            string? manifest = key?.GetValue("Manifest") as string;
            if (string.IsNullOrWhiteSpace(manifest))
            {
                continue;
            }

            string path = manifest!
                .Replace("file:///", "")
                .Replace("|vstolocal", "")
                .Replace('/', '\\');
            string? directory = Path.GetDirectoryName(path);
            if (directory != null)
            {
                return directory;
            }
        }

        return null;
    }

    private static readonly string[] RegistryPaths =
    {
        @"Software\Microsoft\Office\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
        @"Software\Microsoft\Office\16.0\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
        @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
        @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
    };
}
