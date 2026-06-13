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
    public const string MetadataControlTagPrefix = "latexsnipper-eqm-";
    public const string MetadataControlAliasPrefix = "LaTeXSnipperEqMeta-";
    private const string MetadataVariablePrefix = "LaTeXSnipper.Equation.";
    private const string OleNaturalSizeVariablePrefix = "LaTeXSnipper.OleNaturalSize.";
    private const string OmmlNaturalFontSizeVariablePrefix = "LaTeXSnipper.OmmlNaturalFontSize.";
    private const string AutoNumberCounterKey = "LaTeXSnipper.AutoNumberCounter";
    private const string AutoNumberChapterKey = "LaTeXSnipper.AutoNumberChapter";
    private const string AutoNumberSectionKey = "LaTeXSnipper.AutoNumberSection";

    public static string BuildEquationTag(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return EquationTagPrefix + equationId;
    }

    public static string EquationIdFromTag(string tag)
    {
        if (string.IsNullOrWhiteSpace(tag) || !tag.StartsWith(EquationTagPrefix, StringComparison.Ordinal))
        {
            return string.Empty;
        }

        return tag.Substring(EquationTagPrefix.Length);
    }

    public static string BuildNumberTag(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return NumberControlTagPrefix + equationId;
    }

    public static string BuildNumberAlias(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return NumberControlAliasPrefix + equationId;
    }

    public static string BuildMetadataTag(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return MetadataControlTagPrefix + equationId;
    }

    public static string BuildMetadataAlias(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return MetadataControlAliasPrefix + equationId;
    }

    public static string EquationIdFromNumberTag(string tag)
    {
        if (string.IsNullOrWhiteSpace(tag) || !tag.StartsWith(NumberControlTagPrefix, StringComparison.Ordinal))
        {
            return string.Empty;
        }

        return tag.Substring(NumberControlTagPrefix.Length);
    }

    public static string EquationIdFromMetadataTag(string tag)
    {
        if (string.IsNullOrWhiteSpace(tag) || !tag.StartsWith(MetadataControlTagPrefix, StringComparison.Ordinal))
        {
            return string.Empty;
        }

        return tag.Substring(MetadataControlTagPrefix.Length);
    }

    public static string BuildStorageKey(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return MetadataVariablePrefix + equationId;
    }

    public static void Save(dynamic document, FormulaMetadata metadata)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        string key = BuildStorageKey(metadata.Identity.EquationId);
        string json = Serialize(metadata);
        dynamic variables = document.Variables;
        try
        {
            dynamic variable = variables.Item(key);
            variable.Value = json;
        }
        catch
        {
            try
            {
                variables.Add(key, json);
            }
            catch
            {
                // Embedded metadata controls are authoritative and support large formula sources.
            }
        }
    }

    public static FormulaMetadata Load(dynamic document, string equationId)
    {
        FormulaMetadata? embedded = TryLoadEmbedded(document, equationId);
        if (embedded != null)
        {
            return embedded;
        }

        string key = BuildStorageKey(equationId);
        try
        {
            dynamic variable = document.Variables.Item(key);
            return Deserialize(Convert.ToString(variable.Value) ?? string.Empty);
        }
        catch (Exception exc)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"), exc);
        }
    }

    public static void SaveOleNaturalSize(dynamic document, string equationId, double widthPoints, double heightPoints)
    {
        if (widthPoints <= 0 || heightPoints <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(widthPoints), "OLE natural size must be positive.");
        }

        var serializer = new JavaScriptSerializer();
        string json = serializer.Serialize(new Dictionary<string, object>
        {
            ["widthPoints"] = widthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["heightPoints"] = heightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture),
        });
        SaveVariable(document, BuildOleNaturalSizeStorageKey(equationId), json);
    }

    public static bool TryLoadOleNaturalSize(dynamic document, string equationId, out double widthPoints, out double heightPoints)
    {
        widthPoints = 0;
        heightPoints = 0;
        try
        {
            dynamic variable = document.Variables.Item(BuildOleNaturalSizeStorageKey(equationId));
            var serializer = new JavaScriptSerializer();
            var dto = serializer.Deserialize<Dictionary<string, object>>(Convert.ToString(variable.Value) ?? string.Empty);
            widthPoints = ReadDouble(dto, "widthPoints");
            heightPoints = ReadDouble(dto, "heightPoints");
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

    private static string BuildOleNaturalSizeStorageKey(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return OleNaturalSizeVariablePrefix + equationId;
    }

    public static string Serialize(FormulaMetadata metadata)
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
        return serializer.Serialize(dto);
    }

    private static FormulaMetadata? TryLoadEmbedded(dynamic document, string equationId)
    {
        try
        {
            dynamic controls = document.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            string expectedTag = BuildMetadataTag(equationId);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                if (!string.Equals(tag, expectedTag, StringComparison.Ordinal))
                {
                    continue;
                }

                dynamic range = control.Range.Duplicate;
                range.TextRetrievalMode.IncludeHiddenText = true;
                string json = CleanContentControlText(Convert.ToString(range.Text) ?? string.Empty);
                return Deserialize(json);
            }
        }
        catch
        {
        }

        return null;
    }

    private static string CleanContentControlText(string value)
    {
        return value
            .Replace("\a", string.Empty)
            .Replace("\r", string.Empty)
            .Replace("\n", string.Empty)
            .Trim();
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
            ReadEnum(dto, "displayMode", FormulaDisplayMode.Display),
            ReadEnum(dto, "numberingMode", NumberingMode.None),
            ReadString(dto, "numberText"),
            ReadEnum(dto, "renderEngine", RenderEngineKind.Omml),
            ReadInt(dto, "schemaVersion", 1),
            ReadString(dto, "fontColor"),
            ReadEnum(dto, "fontStyle", FormulaFontStyle.TeX),
            ReadDouble(dto, "fontScale"));
    }

    private static string ReadString(Dictionary<string, object> dto, string key)
    {
        return dto.TryGetValue(key, out object value) ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }

    private static int ReadInt(Dictionary<string, object> dto, string key, int fallback)
    {
        if (!dto.TryGetValue(key, out object value))
        {
            return fallback;
        }

        return int.TryParse(Convert.ToString(value), out int parsed) ? parsed : fallback;
    }

    private static double ReadDouble(Dictionary<string, object> dto, string key)
    {
        return dto.TryGetValue(key, out object value)
            && double.TryParse(Convert.ToString(value), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double parsed)
            ? parsed
            : 0;
    }

    private static TEnum ReadEnum<TEnum>(Dictionary<string, object> dto, string key, TEnum fallback)
        where TEnum : struct
    {
        if (!dto.TryGetValue(key, out object value))
        {
            return fallback;
        }

        return Enum.TryParse(Convert.ToString(value), ignoreCase: true, out TEnum parsed) ? parsed : fallback;
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
