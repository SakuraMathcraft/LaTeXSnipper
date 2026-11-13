using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Editor;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointPluginSettings
{
    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string InsertionBackendValue = "PowerPointInsertionBackend";

    public PowerPointPluginSettings(
        FormulaInsertionBackend insertionBackend,
        string formulaColor = "#000000",
        FormulaMathStyle formulaMathStyle = FormulaMathStyle.Automatic,
        double formulaFontSizePoints = 12, bool followHostFontSize = false, FormulaTypography? typography = null)
    {
        InsertionBackend = insertionBackend;
        FollowHostFontSize = followHostFontSize;
        FormulaColor = string.IsNullOrWhiteSpace(formulaColor) ? "#000000" : formulaColor;
        FormulaTypography defaults = FormulaTypography.Default;
        Typography = typography ?? new FormulaTypography(defaults.SymbolFontId, defaults.NumberFontFamily, defaults.CjkFontFamily,
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
        FormulaTypographyDefaults preset = new TypographySettingsStore().Load("powerpoint");
        return new PowerPointPluginSettings(backend, preset.Typography.Color, preset.Typography.DefaultMathStyle, preset.Typography.FontSizePoints,
            preset.FollowHostFontSize, preset.Typography);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("无法打开 LaTeXSnipper Office 插件设置。");
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
    }

}
