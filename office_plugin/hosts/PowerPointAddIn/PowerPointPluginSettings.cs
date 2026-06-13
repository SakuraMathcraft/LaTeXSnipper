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

    public PowerPointPluginSettings(
        FormulaInsertionBackend insertionBackend,
        string formulaColor = "#000000",
        FormulaFontStyle formulaFontStyle = FormulaFontStyle.TeX)
    {
        InsertionBackend = insertionBackend;
        FormulaColor = string.IsNullOrWhiteSpace(formulaColor) ? "#000000" : formulaColor;
        FormulaFontStyle = formulaFontStyle;
    }

    public FormulaInsertionBackend InsertionBackend { get; }

    public string FormulaColor { get; }

    public FormulaFontStyle FormulaFontStyle { get; }

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
        return new PowerPointPluginSettings(backend, color, style);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("Unable to open LaTeXSnipper Office plugin settings.");
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
        key.SetValue(FormulaColorValue, FormulaColor, RegistryValueKind.String);
        key.SetValue(FormulaFontStyleValue, FormulaFontStyle.ToString(), RegistryValueKind.String);
    }
}
