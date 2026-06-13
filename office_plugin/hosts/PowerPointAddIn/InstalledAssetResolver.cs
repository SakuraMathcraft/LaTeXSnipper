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
        foreach (string subPath in RegistryPaths)
        {
            string? directory = GetManifestDirectory(subPath);
            if (directory != null)
            {
                return directory;
            }
        }

        string? assemblyDirectory = Path.GetDirectoryName(typeof(InstalledAssetResolver).Assembly.Location);
        return ContainsHostAssets(assemblyDirectory) ? assemblyDirectory : null;
    }

    private static string? GetManifestDirectory(string subPath)
    {
        using RegistryKey? key = Registry.LocalMachine.OpenSubKey(subPath);
        string? manifest = key?.GetValue("Manifest") as string;
        if (string.IsNullOrWhiteSpace(manifest))
        {
            return null;
        }

        string path = manifest!
            .Replace("file:///", "")
            .Replace("|vstolocal", "")
            .Replace('/', '\\');

        string? directory = Path.GetDirectoryName(path);
        return ContainsHostAssets(directory) ? directory : null;
    }

    private static bool ContainsHostAssets(string? directory)
    {
        return !string.IsNullOrWhiteSpace(directory)
            && Directory.Exists(Path.Combine(directory!, "EditorAssets"));
    }
}
