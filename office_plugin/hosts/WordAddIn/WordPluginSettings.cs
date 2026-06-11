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
    private const string IncludeChapterValue = "NumberIncludeChapter";
    private const string IncludeSectionValue = "NumberIncludeSection";
    private const string NumberSeparatorValue = "NumberSeparator";
    private const string FormulaColorValue = "FormulaColor";
    private const string FormulaFontStyleValue = "FormulaFontStyle";
    private const string FormulaWeightPercentValue = "FormulaWeightPercent";
    private const string FormulaScaleValue = "FormulaScale";

    public WordPluginSettings(
        WordNumberPlacement numberPlacement,
        FormulaInsertionBackend insertionBackend,
        WordNumberFormat numberFormat,
        WordNumberEnclosure numberEnclosure,
        bool includeChapter,
        bool includeSection,
        string numberSeparator,
        string formulaColor,
        FormulaFontStyle formulaFontStyle,
        double formulaScale,
        int formulaWeightPercent)
    {
        NumberPlacement = numberPlacement;
        InsertionBackend = insertionBackend;
        NumberFormat = numberFormat;
        NumberEnclosure = numberEnclosure;
        IncludeChapter = includeChapter;
        IncludeSection = includeSection;
        NumberSeparator = string.IsNullOrEmpty(numberSeparator) ? "." : numberSeparator;
        FormulaColor = string.IsNullOrWhiteSpace(formulaColor) ? "#000000" : formulaColor;
        FormulaFontStyle = formulaFontStyle;
        FormulaScale = Math.Max(0.5, Math.Min(5, formulaScale));
        FormulaWeightPercent = formulaWeightPercent is 5 or 10 or 15 ? formulaWeightPercent : 0;
    }

    public WordNumberPlacement NumberPlacement { get; }

    public FormulaInsertionBackend InsertionBackend { get; }

    public WordNumberFormat NumberFormat { get; }

    public WordNumberEnclosure NumberEnclosure { get; }

    public bool IncludeChapter { get; }

    public bool IncludeSection { get; }

    public string NumberSeparator { get; }

    public string FormulaColor { get; }

    public FormulaFontStyle FormulaFontStyle { get; }

    public double FormulaScale { get; }

    public int FormulaWeightPercent { get; }

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
            ReadEnum(key, NumberEnclosureValue, WordNumberEnclosure.Parentheses),
            ReadBoolean(key, IncludeChapterValue),
            ReadBoolean(key, IncludeSectionValue),
            key?.GetValue(NumberSeparatorValue) as string ?? ".",
            key?.GetValue(FormulaColorValue) as string ?? "#000000",
            ReadEnum(key, FormulaFontStyleValue, FormulaFontStyle.Italic),
            ReadDouble(key, FormulaScaleValue, 1),
            ReadWeightPercent(key));
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("Unable to open LaTeXSnipper Office plugin settings.");
        key.SetValue(NumberPlacementValue, NumberPlacement.ToString(), RegistryValueKind.String);
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
        key.SetValue(NumberFormatValue, NumberFormat.ToString(), RegistryValueKind.String);
        key.SetValue(NumberEnclosureValue, NumberEnclosure.ToString(), RegistryValueKind.String);
        key.SetValue(IncludeChapterValue, IncludeChapter ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(IncludeSectionValue, IncludeSection ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(NumberSeparatorValue, NumberSeparator, RegistryValueKind.String);
        key.SetValue(FormulaColorValue, FormulaColor, RegistryValueKind.String);
        key.SetValue(FormulaFontStyleValue, FormulaFontStyle.ToString(), RegistryValueKind.String);
        key.SetValue(FormulaWeightPercentValue, FormulaWeightPercent, RegistryValueKind.DWord);
        key.SetValue(FormulaScaleValue, FormulaScale.ToString(System.Globalization.CultureInfo.InvariantCulture), RegistryValueKind.String);
    }

    private static T ReadEnum<T>(RegistryKey? key, string valueName, T defaultValue)
        where T : struct
    {
        string raw = key?.GetValue(valueName) as string ?? string.Empty;
        return Enum.TryParse(raw, ignoreCase: false, out T parsed) ? parsed : defaultValue;
    }

    private static bool ReadBoolean(RegistryKey? key, string valueName)
    {
        return Convert.ToInt32(key?.GetValue(valueName) ?? 0) != 0;
    }

    private static double ReadDouble(RegistryKey? key, string valueName, double fallback)
    {
        string raw = Convert.ToString(key?.GetValue(valueName), System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty;
        return double.TryParse(raw, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double value)
            ? value
            : fallback;
    }

    private static int ReadWeightPercent(RegistryKey? key)
    {
        int value = Convert.ToInt32(key?.GetValue(FormulaWeightPercentValue) ?? 0);
        return value is 5 or 10 or 15 ? value : 0;
    }
}
