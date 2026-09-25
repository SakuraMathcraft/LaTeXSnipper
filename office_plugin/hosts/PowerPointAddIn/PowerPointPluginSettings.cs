using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointPluginSettings
{
    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string InsertionBackendValue = "PowerPointInsertionBackend";
    private const string FormulaColorValue = "PowerPointFormulaColor";
    private const string FormulaMathStyleValue = "PowerPointFormulaMathStyle";
    private const string FormulaFontSizePointsValue = "PowerPointFormulaFontSizePoints";

    public PowerPointPluginSettings(
        FormulaInsertionBackend insertionBackend,
        string formulaColor = "#000000",
        FormulaMathStyle formulaMathStyle = FormulaMathStyle.Automatic,
        double formulaFontSizePoints = 12, bool followHostFontSize = false)
    {
        InsertionBackend = insertionBackend;
        FollowHostFontSize = followHostFontSize;
        FormulaColor = string.IsNullOrWhiteSpace(formulaColor) ? "#000000" : formulaColor;
        FormulaTypography defaults = FormulaTypography.Default;
        Typography = new FormulaTypography(defaults.SymbolFontId, defaults.NumberFontFamily, defaults.CjkFontFamily,
            formulaMathStyle, formulaFontSizePoints, FormulaColor);
    }

    public FormulaInsertionBackend InsertionBackend { get; }

    public string FormulaColor { get; }

    public FormulaMathStyle FormulaMathStyle => Typography.DefaultMathStyle;

    public double FormulaFontSizePoints => Typography.FontSizePoints;

    public bool FollowHostFontSize { get; }

    public FormulaTypographyDefaults TypographyDefaults => new FormulaTypographyDefaults(Typography, FollowHostFontSize);

    public FormulaTypography Typography { get; }

    public static PowerPointPluginSettings Load()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RegistryPath);
        string raw = key?.GetValue(InsertionBackendValue) as string ?? string.Empty;
        FormulaInsertionBackend backend = raw == FormulaInsertionBackend.PowerPointPng.ToString()
            ? FormulaInsertionBackend.PowerPointPng
            : FormulaInsertionBackend.Ole;
        string color = key?.GetValue(FormulaColorValue) as string ?? "#000000";
        string styleText = key?.GetValue(FormulaMathStyleValue) as string ?? FormulaMathStyle.Automatic.ToString();
        FormulaMathStyle style = Enum.TryParse(styleText, out FormulaMathStyle parsedStyle)
            ? parsedStyle
            : FormulaMathStyle.Automatic;
        double scale = ReadDouble(key, FormulaFontSizePointsValue, defaultValue: 12);
        return new PowerPointPluginSettings(backend, color, style, scale,
            Convert.ToInt32(key?.GetValue("PowerPointFollowHostFontSize") ?? 0) != 0);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("无法打开 LaTeXSnipper Office 插件设置。");
        key.SetValue("PowerPointFollowHostFontSize", FollowHostFontSize ? 1 : 0, RegistryValueKind.DWord);
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
        key.SetValue(FormulaColorValue, FormulaColor, RegistryValueKind.String);
        key.SetValue(FormulaMathStyleValue, FormulaMathStyle.ToString(), RegistryValueKind.String);
        key.SetValue(
            FormulaFontSizePointsValue,
            FormulaFontSizePoints.ToString(System.Globalization.CultureInfo.InvariantCulture),
            RegistryValueKind.String);
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

}
