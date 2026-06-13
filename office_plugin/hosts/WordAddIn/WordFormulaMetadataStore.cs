using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordFormulaMetadataStore
{
    public const string EquationTagPrefix = "latexsnipper-eq-";
    public const string NumberControlTagPrefix = "latexsnipper-eqn-";
    public const string NumberControlAliasPrefix = "LaTeXSnipperEqNum-";
    private const string OmmlNaturalFontSizeVariablePrefix = "LaTeXSnipper.OmmlNaturalFontSize.";
    private const string AutoNumberCounterKey = "LaTeXSnipper.AutoNumberCounter";
    private const string AutoNumberChapterKey = "LaTeXSnipper.AutoNumberChapter";
    private const string AutoNumberSectionKey = "LaTeXSnipper.AutoNumberSection";
    private const string MetadataSeparator = "|";
    private const string MetadataVariablePrefix = "LS.E.";
    private const int MaxWordTagLength = 64;

    public static string BuildEquationTag(string equationId, string revision = "")
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return ValidateTagLength(
            EquationTagPrefix + equationId +
            (string.IsNullOrWhiteSpace(revision) ? string.Empty : MetadataSeparator + revision));
    }

    public static string EquationIdFromTag(string tag)
    {
        if (string.IsNullOrWhiteSpace(tag) || !tag.StartsWith(EquationTagPrefix, StringComparison.Ordinal))
        {
            return string.Empty;
        }

        string value = tag.Substring(EquationTagPrefix.Length);
        int separatorIndex = value.IndexOf(MetadataSeparator, StringComparison.Ordinal);
        return separatorIndex < 0 ? value : value.Substring(0, separatorIndex);
    }

    public static string Save(
        dynamic document,
        FormulaMetadata metadata,
        double naturalWidthPoints = 0,
        double naturalHeightPoints = 0)
    {
        string revision = Guid.NewGuid().ToString("N").Substring(0, 10);
        SaveVariable(
            document,
            BuildMetadataStorageKey(metadata.Identity.EquationId, revision),
            Serialize(metadata, naturalWidthPoints, naturalHeightPoints));
        return BuildEquationTag(metadata.Identity.EquationId, revision);
    }

    public static FormulaMetadata Load(dynamic document, string tag)
    {
        return Deserialize(LoadPayload(document, tag));
    }

    public static string BuildNumberTag(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return ValidateTagLength(NumberControlTagPrefix + equationId);
    }

    public static string BuildNumberAlias(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return ValidateTagLength(NumberControlAliasPrefix + equationId);
    }

    public static string EquationIdFromNumberTag(string tag)
    {
        if (string.IsNullOrWhiteSpace(tag) || !tag.StartsWith(NumberControlTagPrefix, StringComparison.Ordinal))
        {
            return string.Empty;
        }

        return tag.Substring(NumberControlTagPrefix.Length);
    }

    public static bool TryLoadOleNaturalSize(
        dynamic document,
        string tag,
        out double widthPoints,
        out double heightPoints)
    {
        widthPoints = 0;
        heightPoints = 0;
        try
        {
            var serializer = new JavaScriptSerializer();
            var dto = serializer.Deserialize<Dictionary<string, object>>(LoadPayload(document, tag));
            widthPoints = ReadDouble(dto, "naturalWidthPoints");
            heightPoints = ReadDouble(dto, "naturalHeightPoints");
            return widthPoints > 0 && heightPoints > 0;
        }
        catch
        {
            return false;
        }
    }

    public static void SaveOmmlNaturalFontSize(dynamic document, string equationId, double fontSizePoints)
    {
        if (fontSizePoints <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(fontSizePoints), "OMML natural font size must be positive.");
        }

        SaveVariable(
            document,
            OmmlNaturalFontSizeVariablePrefix + equationId,
            fontSizePoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    public static bool TryLoadOmmlNaturalFontSize(dynamic document, string equationId, out double fontSizePoints)
    {
        fontSizePoints = 0;
        try
        {
            dynamic variable = document.Variables.Item(OmmlNaturalFontSizeVariablePrefix + equationId);
            fontSizePoints = Convert.ToDouble(
                variable.Value,
                System.Globalization.CultureInfo.InvariantCulture);
            return fontSizePoints > 0;
        }
        catch
        {
            return false;
        }
    }

    public static string Serialize(
        FormulaMetadata metadata,
        double naturalWidthPoints = 0,
        double naturalHeightPoints = 0)
    {
        var serializer = new JavaScriptSerializer();
        var dto = new Dictionary<string, object>
        {
            ["schemaVersion"] = metadata.SchemaVersion,
            ["documentId"] = metadata.Identity.DocumentId,
            ["equationId"] = metadata.Identity.EquationId,
            ["latex"] = metadata.Latex,
            ["displayMode"] = metadata.DisplayMode.ToString(),
            ["numberingMode"] = metadata.NumberingMode.ToString(),
            ["numberText"] = metadata.NumberText,
            ["renderEngine"] = metadata.RenderEngine.ToString(),
            ["fontColor"] = metadata.FontColor,
            ["fontStyle"] = metadata.FontStyle.ToString(),
            ["fontScale"] = metadata.FontScale,
        };
        if (naturalWidthPoints > 0 && naturalHeightPoints > 0)
        {
            dto["naturalWidthPoints"] = naturalWidthPoints;
            dto["naturalHeightPoints"] = naturalHeightPoints;
        }

        return serializer.Serialize(dto);
    }

    private static string LoadPayload(dynamic document, string tag)
    {
        string equationId = EquationIdFromTag(tag);
        string revision = RevisionFromTag(tag);
        if (string.IsNullOrWhiteSpace(equationId) || string.IsNullOrWhiteSpace(revision))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        try
        {
            dynamic variable = document.Variables.Item(BuildMetadataStorageKey(equationId, revision));
            return Convert.ToString(variable.Value) ?? string.Empty;
        }
        catch (Exception exc)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"), exc);
        }
    }

    private static string RevisionFromTag(string tag)
    {
        int separatorIndex = tag.IndexOf(MetadataSeparator, StringComparison.Ordinal);
        return separatorIndex < 0 || separatorIndex == tag.Length - 1
            ? string.Empty
            : tag.Substring(separatorIndex + MetadataSeparator.Length);
    }

    private static string BuildMetadataStorageKey(string equationId, string revision)
    {
        return MetadataVariablePrefix + equationId + "." + revision;
    }

    public static FormulaMetadata Deserialize(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        var serializer = new JavaScriptSerializer();
        var dto = serializer.Deserialize<Dictionary<string, object>>(json);
        string documentId = ReadString(dto, "documentId");
        string equationId = ReadString(dto, "equationId");
        return new FormulaMetadata(
            new FormulaIdentity(documentId, equationId),
            ReadString(dto, "latex"),
            ReadEnum<FormulaDisplayMode>(dto, "displayMode"),
            ReadEnum<NumberingMode>(dto, "numberingMode"),
            ReadString(dto, "numberText"),
            ReadEnum<RenderEngineKind>(dto, "renderEngine"),
            ReadInt(dto, "schemaVersion"),
            ReadString(dto, "fontColor"),
            ReadEnum<FormulaFontStyle>(dto, "fontStyle"),
            ReadRequiredDouble(dto, "fontScale"));
    }

    private static string ReadString(Dictionary<string, object> dto, string key)
    {
        if (!dto.TryGetValue(key, out object value))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return Convert.ToString(value) ?? string.Empty;
    }

    private static int ReadInt(Dictionary<string, object> dto, string key)
    {
        if (!dto.TryGetValue(key, out object value) ||
            !int.TryParse(Convert.ToString(value), out int parsed))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return parsed;
    }

    private static double ReadDouble(Dictionary<string, object> dto, string key)
    {
        return dto.TryGetValue(key, out object value)
            && double.TryParse(Convert.ToString(value), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double parsed)
            ? parsed
            : 0;
    }

    private static double ReadRequiredDouble(Dictionary<string, object> dto, string key)
    {
        double value = ReadDouble(dto, key);
        if (value <= 0)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return value;
    }

    private static TEnum ReadEnum<TEnum>(Dictionary<string, object> dto, string key)
        where TEnum : struct
    {
        if (!dto.TryGetValue(key, out object value) ||
            !Enum.TryParse(Convert.ToString(value), ignoreCase: true, out TEnum parsed))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return parsed;
    }

    private static string ValidateTagLength(string tag)
    {
        if (tag.Length > MaxWordTagLength)
        {
            throw new InvalidOperationException("Word formula tag exceeds the 64-character limit.");
        }

        return tag;
    }

    public static int GetAutoNumberCounter(dynamic document)
    {
        try
        {
            dynamic variable = document.Variables.Item(AutoNumberCounterKey);
            return Convert.ToInt32(variable.Value, System.Globalization.CultureInfo.InvariantCulture);
        }
        catch
        {
            return 1;
        }
    }

    public static void SetAutoNumberCounter(dynamic document, int value)
    {
        SetIntegerVariable(document, AutoNumberCounterKey, value);
    }

    public static int GetAutoNumberChapter(dynamic document)
    {
        return GetIntegerVariable(document, AutoNumberChapterKey, 1);
    }

    public static void SetAutoNumberChapter(dynamic document, int value)
    {
        SetIntegerVariable(document, AutoNumberChapterKey, value);
    }

    public static int GetAutoNumberSection(dynamic document)
    {
        return GetIntegerVariable(document, AutoNumberSectionKey, 1);
    }

    public static void SetAutoNumberSection(dynamic document, int value)
    {
        SetIntegerVariable(document, AutoNumberSectionKey, value);
    }

    private static int GetIntegerVariable(dynamic document, string key, int fallback)
    {
        try
        {
            dynamic variable = document.Variables.Item(key);
            return Convert.ToInt32(variable.Value, System.Globalization.CultureInfo.InvariantCulture);
        }
        catch
        {
            return fallback;
        }
    }

    private static void SetIntegerVariable(dynamic document, string key, int value)
    {
        SaveVariable(
            document,
            key,
            value.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private static void SaveVariable(dynamic document, string key, string value)
    {
        dynamic variables = document.Variables;
        try
        {
            dynamic variable = variables.Item(key);
            variable.Value = value;
        }
        catch
        {
            variables.Add(key, value);
        }
    }

}
