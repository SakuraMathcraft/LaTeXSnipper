using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordPluginSettings
{
    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string NumberPlacementValue = "NumberPlacement";
    private const string InsertionBackendValue = "WordInsertionBackend";

    public WordPluginSettings(WordNumberPlacement numberPlacement, FormulaInsertionBackend insertionBackend)
    {
        NumberPlacement = numberPlacement;
        InsertionBackend = insertionBackend;
    }

    public WordNumberPlacement NumberPlacement { get; }

    public FormulaInsertionBackend InsertionBackend { get; }

    public static WordPluginSettings Load()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RegistryPath);
        string raw = key?.GetValue(NumberPlacementValue) as string ?? string.Empty;
        string backendRaw = key?.GetValue(InsertionBackendValue) as string ?? string.Empty;
        FormulaInsertionBackend backend = backendRaw == FormulaInsertionBackend.WordOmml.ToString()
            ? FormulaInsertionBackend.WordOmml
            : FormulaInsertionBackend.Ole;
        return new WordPluginSettings(raw == "Left" ? WordNumberPlacement.Left : WordNumberPlacement.Right, backend);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("Unable to open LaTeXSnipper Office plugin settings.");
        key.SetValue(NumberPlacementValue, NumberPlacement.ToString(), RegistryValueKind.String);
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
    }
}
