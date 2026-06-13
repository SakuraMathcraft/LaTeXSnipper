using System.IO;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal static class InstalledAssetResolver
{
    public static string? FindAssetRoot(string assetFile)
    {
        string? installDirectory = FindInstallDirectory();
        if (installDirectory == null)
        {
            return null;
        }

        string candidate = Path.Combine(installDirectory, "EditorAssets");
        return File.Exists(Path.Combine(candidate, assetFile)) ? candidate : null;
    }

    private static readonly string[] RegistryPaths =
    {
        @"Software\Microsoft\Office\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
        @"Software\Microsoft\Office\16.0\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
        @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
        @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
    };

    public static string? FindInstallDirectory()
    {
        string? assemblyDirectory = Path.GetDirectoryName(typeof(InstalledAssetResolver).Assembly.Location);
        if (!string.IsNullOrWhiteSpace(assemblyDirectory))
        {
            return assemblyDirectory;
        }

        foreach (string subPath in RegistryPaths)
        {
            string? directory = GetManifestDirectory(Registry.LocalMachine, subPath);
            if (directory != null)
            {
                return directory;
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
}
