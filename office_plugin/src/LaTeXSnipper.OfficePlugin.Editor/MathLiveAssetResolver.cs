#if NET48
using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.Editor;

internal static class MathLiveAssetResolver
{
    public static string FindAssetRoot(MathLiveFormulaEditorOptions options, string assetFile)
    {
        return FindAssetRoot(options.DevAssetRelativePaths, options.RegistryPaths, "EditorAssets", assetFile);
    }

    public static string FindSharedAssetRoot(MathLiveFormulaEditorOptions options, string assetFile)
    {
        return FindAssetRoot(options.SharedDevAssetRelativePaths, options.RegistryPaths, "EditorSharedAssets", assetFile);
    }

    private static string FindAssetRoot(
        IReadOnlyList<string> devAssetRelativePaths,
        IReadOnlyList<string> registryPaths,
        string copiedFolderName,
        string assetFile)
    {
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;
        string copied = Path.Combine(baseDirectory, copiedFolderName);
        if (File.Exists(Path.Combine(copied, assetFile)))
        {
            return copied;
        }

        string? current = baseDirectory;
        for (int i = 0; i < 8 && current != null; i++)
        {
            foreach (string relativePath in devAssetRelativePaths)
            {
                string candidate = Path.Combine(current, relativePath);
                if (File.Exists(Path.Combine(candidate, assetFile)))
                {
                    return candidate;
                }
            }

            current = Directory.GetParent(current)?.FullName;
        }

        foreach (RegistryKey root in new[] { Registry.LocalMachine, Registry.CurrentUser })
        {
            foreach (string subPath in registryPaths)
            {
                string? manifestDirectory = GetManifestDirectory(root, subPath);
                if (manifestDirectory == null)
                {
                    continue;
                }

                string candidate = Path.Combine(manifestDirectory, copiedFolderName);
                if (File.Exists(Path.Combine(candidate, assetFile)))
                {
                    return candidate;
                }
            }
        }

        throw new DirectoryNotFoundException("MathLive editor assets were not found.");
    }

    private static string? GetManifestDirectory(RegistryKey root, string subPath)
    {
        using RegistryKey? key = root.OpenSubKey(subPath);
        string? manifest = key?.GetValue("Manifest") as string;
        if (string.IsNullOrWhiteSpace(manifest))
        {
            return null;
        }

        string manifestValue = manifest!;
        string path = manifestValue
            .Replace("file:///", string.Empty)
            .Replace("|vstolocal", string.Empty)
            .Replace('/', '\\');
        return Path.GetDirectoryName(path);
    }
}
#endif
