using System;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordPluginSettings
{
    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string NumberPlacementValue = "NumberPlacement";

    public WordPluginSettings(WordNumberPlacement numberPlacement)
    {
        NumberPlacement = numberPlacement;
    }

    public WordNumberPlacement NumberPlacement { get; }

    public static WordPluginSettings Load()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RegistryPath);
        string raw = key?.GetValue(NumberPlacementValue) as string ?? string.Empty;
        return new WordPluginSettings(raw == "Left" ? WordNumberPlacement.Left : WordNumberPlacement.Right);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("Unable to open LaTeXSnipper Office plugin settings.");
        key.SetValue(NumberPlacementValue, NumberPlacement.ToString(), RegistryValueKind.String);
    }
}
