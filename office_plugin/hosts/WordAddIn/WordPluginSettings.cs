using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Editor;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordPluginSettings
{
    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string NumberPlacementValue = "NumberPlacement";
    private const string NumberEnclosureValue = "NumberEnclosure";
    private const string InsertionBackendValue = "WordInsertionBackend";
    private const string IncludeChapterValue = "NumberIncludeChapter";
    private const string IncludeSectionValue = "NumberIncludeSection";
    private const string HideChapterBoundaryValue = "HideChapterBoundary";
    private const string HideSectionBoundaryValue = "HideSectionBoundary";
    private const string NumberSeparatorValue = "NumberSeparator";

    public WordPluginSettings(
        WordNumberPlacement numberPlacement,
        FormulaInsertionBackend insertionBackend,
        WordNumberEnclosure numberEnclosure,
        bool includeChapter,
        bool includeSection,
        bool hideChapterBoundary,
        bool hideSectionBoundary,
        string numberSeparator,
        string formulaColor,
        FormulaMathStyle formulaMathStyle,
        double formulaFontSizePoints, bool followHostFontSize = false, FormulaTypography? typography = null)
    {
        NumberPlacement = numberPlacement;
        InsertionBackend = insertionBackend;
        FollowHostFontSize = followHostFontSize;
        NumberEnclosure = numberEnclosure;
        IncludeChapter = includeChapter;
        IncludeSection = includeSection;
        HideChapterBoundary = hideChapterBoundary;
        HideSectionBoundary = hideSectionBoundary;
        NumberSeparator = NormalizeNumberSeparator(numberSeparator);
        FormulaColor = string.IsNullOrWhiteSpace(formulaColor) ? "#000000" : formulaColor;
        FormulaTypography defaults = FormulaTypography.Default;
        Typography = typography ?? new FormulaTypography(defaults.SymbolFontId, defaults.NumberFontFamily, defaults.CjkFontFamily,
            formulaMathStyle, formulaFontSizePoints, FormulaColor);
    }

    public WordNumberPlacement NumberPlacement { get; }

    public FormulaInsertionBackend InsertionBackend { get; }

    public WordNumberEnclosure NumberEnclosure { get; }

    public bool IncludeChapter { get; }

    public bool IncludeSection { get; }

    public bool HideChapterBoundary { get; }

    public bool HideSectionBoundary { get; }

    public string NumberSeparator { get; }

    public string FormulaColor { get; }

    public FormulaMathStyle FormulaMathStyle => Typography.DefaultMathStyle;

    public double FormulaFontSizePoints => Typography.FontSizePoints;

    public bool FollowHostFontSize { get; }

    public FormulaTypographyDefaults TypographyDefaults => new FormulaTypographyDefaults(Typography, FollowHostFontSize);

    public FormulaTypography Typography { get; }

    public static WordPluginSettings Load()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RegistryPath);
        string placementRaw = key?.GetValue(NumberPlacementValue) as string ?? string.Empty;
        string backendRaw = key?.GetValue(InsertionBackendValue) as string ?? string.Empty;
        FormulaInsertionBackend backend = backendRaw == FormulaInsertionBackend.WordOmml.ToString()
            ? FormulaInsertionBackend.WordOmml
            : FormulaInsertionBackend.Ole;
        FormulaTypographyDefaults preset = new TypographySettingsStore().Load("word");
        return new WordPluginSettings(
            placementRaw == "Left" ? WordNumberPlacement.Left : WordNumberPlacement.Right,
            backend,
            ReadEnum(key, NumberEnclosureValue, WordNumberEnclosure.Parentheses),
            ReadBoolean(key, IncludeChapterValue),
            ReadBoolean(key, IncludeSectionValue),
            ReadBoolean(key, HideChapterBoundaryValue),
            ReadBoolean(key, HideSectionBoundaryValue),
            key?.GetValue(NumberSeparatorValue) as string ?? "-",
            preset.Typography.Color,
            preset.Typography.DefaultMathStyle,
            preset.Typography.FontSizePoints,
            preset.FollowHostFontSize, preset.Typography);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("无法打开 LaTeXSnipper Office 插件设置。");
        key.SetValue(NumberPlacementValue, NumberPlacement.ToString(), RegistryValueKind.String);
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
        key.SetValue(NumberEnclosureValue, NumberEnclosure.ToString(), RegistryValueKind.String);
        key.SetValue(IncludeChapterValue, IncludeChapter ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(IncludeSectionValue, IncludeSection ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(HideChapterBoundaryValue, HideChapterBoundary ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(HideSectionBoundaryValue, HideSectionBoundary ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(NumberSeparatorValue, NumberSeparator, RegistryValueKind.String);
    }

    private static T ReadEnum<T>(RegistryKey? key, string valueName, T defaultValue)
        where T : struct
    {
        string raw = key?.GetValue(valueName) as string ?? string.Empty;
        return Enum.TryParse(raw, ignoreCase: false, out T parsed) ? parsed : defaultValue;
    }

    private static bool ReadBoolean(RegistryKey? key, string valueName, bool defaultValue = false)
    {
        object? value = key?.GetValue(valueName);
        return value == null ? defaultValue : Convert.ToInt32(value) != 0;
    }

    private static string NormalizeNumberSeparator(string value)
    {
        return value is "-" or "." or "·" or ":" or "/" ? value : "-";
    }

}
