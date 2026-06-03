using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordPluginSettings
{
    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string NumberPlacementValue = "NumberPlacement";
    private const string NumberFormatValue = "NumberFormat";
    private const string NumberEnclosureValue = "NumberEnclosure";
    private const string InsertionBackendValue = "WordInsertionBackend";

    public WordPluginSettings(
        WordNumberPlacement numberPlacement,
        FormulaInsertionBackend insertionBackend,
        WordNumberFormat numberFormat,
        WordNumberEnclosure numberEnclosure)
    {
        NumberPlacement = numberPlacement;
        InsertionBackend = insertionBackend;
        NumberFormat = numberFormat;
        NumberEnclosure = numberEnclosure;
    }

    public WordNumberPlacement NumberPlacement { get; }

    public FormulaInsertionBackend InsertionBackend { get; }

    public WordNumberFormat NumberFormat { get; }

    public WordNumberEnclosure NumberEnclosure { get; }

    public static WordPluginSettings Load()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RegistryPath);
        string placementRaw = key?.GetValue(NumberPlacementValue) as string ?? string.Empty;
        string backendRaw = key?.GetValue(InsertionBackendValue) as string ?? string.Empty;
        FormulaInsertionBackend backend = backendRaw == FormulaInsertionBackend.WordOmml.ToString()
            ? FormulaInsertionBackend.WordOmml
            : FormulaInsertionBackend.Ole;
        return new WordPluginSettings(
            placementRaw == "Left" ? WordNumberPlacement.Left : WordNumberPlacement.Right,
            backend,
            ReadEnum(key, NumberFormatValue, WordNumberFormat.Arabic),
            ReadEnum(key, NumberEnclosureValue, WordNumberEnclosure.Parentheses));
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("Unable to open LaTeXSnipper Office plugin settings.");
        key.SetValue(NumberPlacementValue, NumberPlacement.ToString(), RegistryValueKind.String);
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
        key.SetValue(NumberFormatValue, NumberFormat.ToString(), RegistryValueKind.String);
        key.SetValue(NumberEnclosureValue, NumberEnclosure.ToString(), RegistryValueKind.String);
    }

    private static T ReadEnum<T>(RegistryKey? key, string valueName, T defaultValue)
        where T : struct
    {
        string raw = key?.GetValue(valueName) as string ?? string.Empty;
        return Enum.TryParse(raw, ignoreCase: false, out T parsed) ? parsed : defaultValue;
    }
}
