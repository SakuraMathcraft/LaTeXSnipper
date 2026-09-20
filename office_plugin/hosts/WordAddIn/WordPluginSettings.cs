using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
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
    private const string FormulaColorValue = "FormulaColor";
    private const string UseSystemFormulaColorValue = "UseSystemFormulaColor";
    private const string FormulaMathStyleValue = "FormulaMathStyle";
    private const string FormulaFontSizePointsValue = "FormulaFontSizePoints";

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
        bool useSystemFormulaColor,
        FormulaMathStyle formulaMathStyle,
        double formulaFontSizePoints, bool followHostFontSize = false)
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
        UseSystemFormulaColor = useSystemFormulaColor;
        FormulaColor = useSystemFormulaColor
            ? WordFormulaColorDefaults.Current
            : string.IsNullOrWhiteSpace(formulaColor) ? WordFormulaColorDefaults.Current : formulaColor;
        FormulaTypography defaults = FormulaTypography.Default;
        Typography = new FormulaTypography(defaults.SymbolFontId, defaults.NumberFontFamily, defaults.CjkFontFamily,
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

    public bool UseSystemFormulaColor { get; }

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
        return new WordPluginSettings(
            placementRaw == "Left" ? WordNumberPlacement.Left : WordNumberPlacement.Right,
            backend,
            ReadEnum(key, NumberEnclosureValue, WordNumberEnclosure.Parentheses),
            ReadBoolean(key, IncludeChapterValue),
            ReadBoolean(key, IncludeSectionValue),
            ReadBoolean(key, HideChapterBoundaryValue),
            ReadBoolean(key, HideSectionBoundaryValue),
            key?.GetValue(NumberSeparatorValue) as string ?? "-",
            key?.GetValue(FormulaColorValue) as string ?? WordFormulaColorDefaults.Current,
            ReadBoolean(key, UseSystemFormulaColorValue, defaultValue: true),
            ReadEnum(key, FormulaMathStyleValue, FormulaMathStyle.Automatic),
            ReadDouble(key, FormulaFontSizePointsValue, defaultValue: 12),
            ReadBoolean(key, "WordFollowHostFontSize"));
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("无法打开 LaTeXSnipper Office 插件设置。");
        key.SetValue(NumberPlacementValue, NumberPlacement.ToString(), RegistryValueKind.String);
        key.SetValue("WordFollowHostFontSize", FollowHostFontSize ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
        key.SetValue(NumberEnclosureValue, NumberEnclosure.ToString(), RegistryValueKind.String);
        key.SetValue(IncludeChapterValue, IncludeChapter ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(IncludeSectionValue, IncludeSection ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(HideChapterBoundaryValue, HideChapterBoundary ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(HideSectionBoundaryValue, HideSectionBoundary ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(NumberSeparatorValue, NumberSeparator, RegistryValueKind.String);
        key.SetValue(FormulaColorValue, FormulaColor, RegistryValueKind.String);
        key.SetValue(UseSystemFormulaColorValue, UseSystemFormulaColor ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(FormulaMathStyleValue, FormulaMathStyle.ToString(), RegistryValueKind.String);
        key.SetValue(
            FormulaFontSizePointsValue,
            FormulaFontSizePoints.ToString(System.Globalization.CultureInfo.InvariantCulture),
            RegistryValueKind.String);
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

    private static double ReadDouble(RegistryKey? key, string valueName, double defaultValue)
    {
        object? value = key?.GetValue(valueName);
        return value != null &&
            double.TryParse(
                Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture),
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture,
                out double parsed)
            ? parsed
            : defaultValue;
    }

    private static string NormalizeNumberSeparator(string value)
    {
        return value is "-" or "." or "·" or ":" or "/" ? value : "-";
    }

}
