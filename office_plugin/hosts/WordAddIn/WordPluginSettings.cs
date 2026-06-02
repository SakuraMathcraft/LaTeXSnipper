using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordPluginSettings
{
    public const double MinOleScaleExclusive = 0;
    public const double MaxOleScale = 5;

    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string NumberPlacementValue = "NumberPlacement";
    private const string InsertionBackendValue = "WordInsertionBackend";
    private const string OleScaleValue = "WordOleScale";

    public WordPluginSettings(WordNumberPlacement numberPlacement, FormulaInsertionBackend insertionBackend, double oleScale)
    {
        ValidateOleScale(oleScale);
        NumberPlacement = numberPlacement;
        InsertionBackend = insertionBackend;
        OleScale = oleScale;
    }

    public WordNumberPlacement NumberPlacement { get; }

    public FormulaInsertionBackend InsertionBackend { get; }

    public double OleScale { get; }

    public static WordPluginSettings Load()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RegistryPath);
        string raw = key?.GetValue(NumberPlacementValue) as string ?? string.Empty;
        string backendRaw = key?.GetValue(InsertionBackendValue) as string ?? string.Empty;
        string scaleRaw = key?.GetValue(OleScaleValue) as string ?? string.Empty;
        FormulaInsertionBackend backend = backendRaw == FormulaInsertionBackend.WordOmml.ToString()
            ? FormulaInsertionBackend.WordOmml
            : FormulaInsertionBackend.Ole;
        double scale = double.TryParse(scaleRaw, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double parsedScale) && IsValidOleScale(parsedScale)
            ? parsedScale
            : 1;
        return new WordPluginSettings(raw == "Left" ? WordNumberPlacement.Left : WordNumberPlacement.Right, backend, scale);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("Unable to open LaTeXSnipper Office plugin settings.");
        key.SetValue(NumberPlacementValue, NumberPlacement.ToString(), RegistryValueKind.String);
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
        key.SetValue(OleScaleValue, OleScale.ToString(System.Globalization.CultureInfo.InvariantCulture), RegistryValueKind.String);
    }

    public static bool IsValidOleScale(double value)
    {
        return value > MinOleScaleExclusive && value <= MaxOleScale;
    }

    public static void ValidateOleScale(double value)
    {
        if (!IsValidOleScale(value))
        {
            throw new ArgumentOutOfRangeException(nameof(value), "OLE initial scale must be greater than 0 and less than or equal to 5.");
        }
    }
}
