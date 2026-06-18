using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointPluginSettings
{
    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string InsertionBackendValue = "PowerPointInsertionBackend";
    private const string FormulaColorValue = "PowerPointFormulaColor";
    private const string FormulaFontStyleValue = "PowerPointFormulaFontStyle";
    private const string FormulaFontScaleValue = "PowerPointFormulaFontScale";
    private const double MinimumFormulaFontScale = 1.0;
    private const double MaximumFormulaFontScale = 1.5;

    public PowerPointPluginSettings(
        FormulaInsertionBackend insertionBackend,
        string formulaColor = "#000000",
        FormulaFontStyle formulaFontStyle = FormulaFontStyle.TeX,
        double formulaFontScale = 1)
    {
        InsertionBackend = insertionBackend;
        FormulaColor = string.IsNullOrWhiteSpace(formulaColor) ? "#000000" : formulaColor;
        FormulaFontStyle = formulaFontStyle;
        FormulaFontScale = ClampFormulaFontScale(formulaFontScale);
    }

    public FormulaInsertionBackend InsertionBackend { get; }

    public string FormulaColor { get; }

    public FormulaFontStyle FormulaFontStyle { get; }

    public double FormulaFontScale { get; }

    public static PowerPointPluginSettings Load()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RegistryPath);
        string raw = key?.GetValue(InsertionBackendValue) as string ?? string.Empty;
        FormulaInsertionBackend backend = raw == FormulaInsertionBackend.PowerPointPng.ToString()
            ? FormulaInsertionBackend.PowerPointPng
            : FormulaInsertionBackend.Ole;
        string color = key?.GetValue(FormulaColorValue) as string ?? "#000000";
        string styleText = key?.GetValue(FormulaFontStyleValue) as string ?? FormulaFontStyle.TeX.ToString();
        FormulaFontStyle style = Enum.TryParse(styleText, out FormulaFontStyle parsedStyle)
            ? parsedStyle
            : FormulaFontStyle.TeX;
        double scale = ReadDouble(key, FormulaFontScaleValue, defaultValue: 1);
        return new PowerPointPluginSettings(backend, color, style, scale);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("Unable to open LaTeXSnipper Office plugin settings.");
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
        key.SetValue(FormulaColorValue, FormulaColor, RegistryValueKind.String);
        key.SetValue(FormulaFontStyleValue, FormulaFontStyle.ToString(), RegistryValueKind.String);
        key.SetValue(
            FormulaFontScaleValue,
            FormulaFontScale.ToString(System.Globalization.CultureInfo.InvariantCulture),
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

    private static double ClampFormulaFontScale(double value)
    {
        if (double.IsNaN(value) || double.IsInfinity(value))
        {
            return MinimumFormulaFontScale;
        }

        return Math.Max(MinimumFormulaFontScale, Math.Min(MaximumFormulaFontScale, value));
    }
}
