using System;
using System.Collections.Generic;
using System.Text;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordFormulaMetadataStore
{
    public const string EquationTagPrefix = "latexsnipper-eq-";
    internal const string MetadataControlTag = "latexsnipper-metadata-v2";
    private const string MetadataPayloadPrefix = "LaTeXSnipper.Metadata.v2:";
    private const int MaxWordTagLength = 64;

    public static string BuildEquationTag(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return ValidateTagLength(EquationTagPrefix + equationId);
    }

    public static string EquationIdFromTag(string tag)
    {
        return !string.IsNullOrWhiteSpace(tag)
            && tag.StartsWith(EquationTagPrefix, StringComparison.Ordinal)
            ? tag.Substring(EquationTagPrefix.Length)
            : string.Empty;
    }

    public static void SaveOmml(dynamic control, FormulaMetadata metadata, double naturalFontSizePoints)
    {
        ValidateMetadata(metadata, RenderEngineKind.Omml);
        ValidateDocumentIdentity(control.Range.Document, metadata);
        if (naturalFontSizePoints <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(naturalFontSizePoints));
        }

        control.Tag = BuildEquationTag(metadata.Identity.EquationId);
        control.Title = "LaTeXSnipper Equation";
        string payload = EncodePayload(Serialize(metadata, naturalFontSizePoints: naturalFontSizePoints));
        dynamic? metadataControl = FindMetadataControl(control);
        if (metadataControl == null)
        {
            throw MetadataMissing();
        }

        metadataControl.LockContents = false;
        metadataControl.LockContentControl = false;
        metadataControl.Range.Text = payload;
        metadataControl.Range.Font.Hidden = -1;
        metadataControl.Range.Font.Size = 1;
        metadataControl.Range.NoProofing = 1;
    }

    public static void SaveOle(
        dynamic inlineShape,
        FormulaMetadata metadata,
        double naturalWidthPoints,
        double naturalHeightPoints)
    {
        ValidateMetadata(metadata, RenderEngineKind.MathJaxSvg);
        ValidateDocumentIdentity(inlineShape.Range.Document, metadata);
        if (naturalWidthPoints <= 0 || naturalHeightPoints <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(naturalWidthPoints));
        }

        inlineShape.Title = BuildEquationTag(metadata.Identity.EquationId);
        inlineShape.AlternativeText = EncodePayload(Serialize(
            metadata,
            naturalWidthPoints,
            naturalHeightPoints));
    }

    public static FormulaMetadata LoadOmml(dynamic control)
    {
        MetadataRecord record = DeserializeRecord(ReadOmmlPayload(control));
        ValidateStoredRecord(record, RenderEngineKind.Omml);
        ValidateStoredIdentity(Convert.ToString(control.Tag), record);

        return record.Metadata;
    }

    public static FormulaMetadata LoadOle(dynamic inlineShape)
    {
        MetadataRecord record = DeserializeRecord(ReadOlePayload(inlineShape));
        ValidateStoredRecord(record, RenderEngineKind.MathJaxSvg);
        ValidateStoredIdentity(Convert.ToString(inlineShape.Title), record);

        return record.Metadata;
    }

    public static bool TryLoadOmmlNaturalFontSize(dynamic control, out double fontSizePoints)
    {
        fontSizePoints = 0;
        try
        {
            MetadataRecord record = DeserializeRecord(ReadOmmlPayload(control));
            ValidateStoredRecord(record, RenderEngineKind.Omml);
            ValidateStoredIdentity(Convert.ToString(control.Tag), record);
            fontSizePoints = record.NaturalFontSizePoints;
            return fontSizePoints > 0;
        }
        catch
        {
            return false;
        }
    }

    public static bool TryLoadOleNaturalSize(
        dynamic inlineShape,
        out double widthPoints,
        out double heightPoints)
    {
        widthPoints = 0;
        heightPoints = 0;
        try
        {
            MetadataRecord record = DeserializeRecord(ReadOlePayload(inlineShape));
            ValidateStoredRecord(record, RenderEngineKind.MathJaxSvg);
            ValidateStoredIdentity(Convert.ToString(inlineShape.Title), record);
            widthPoints = record.NaturalWidthPoints;
            heightPoints = record.NaturalHeightPoints;
            return widthPoints > 0 && heightPoints > 0;
        }
        catch
        {
            return false;
        }
    }

    private static string Serialize(
        FormulaMetadata metadata,
        double naturalWidthPoints = 0,
        double naturalHeightPoints = 0,
        double naturalFontSizePoints = 0)
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
            ["fontScale"] = metadata.FontScale,
        };
        if (naturalWidthPoints > 0 && naturalHeightPoints > 0)
        {
            dto["naturalWidthPoints"] = naturalWidthPoints;
            dto["naturalHeightPoints"] = naturalHeightPoints;
        }

        if (naturalFontSizePoints > 0)
        {
            dto["naturalFontSizePoints"] = naturalFontSizePoints;
        }

        return serializer.Serialize(dto);
    }

    private static dynamic? FindMetadataControl(dynamic formulaControl)
    {
        dynamic controls = formulaControl.Range.ContentControls;
        dynamic? found = null;
        int count = Convert.ToInt32(controls.Count);
        for (int index = 1; index <= count; index++)
        {
            dynamic candidate = controls.Item(index);
            if (!string.Equals(
                Convert.ToString(candidate.Tag),
                MetadataControlTag,
                StringComparison.Ordinal))
            {
                continue;
            }

            if (found != null)
            {
                throw MetadataMissing();
            }

            found = candidate;
        }

        return found;
    }

    private static string ReadOmmlPayload(dynamic control)
    {
        dynamic? metadataControl = FindMetadataControl(control);
        if (metadataControl == null)
        {
            throw MetadataMissing();
        }

        dynamic payloadRange = metadataControl.Range.Duplicate;
        payloadRange.TextRetrievalMode.IncludeHiddenText = true;
        return DecodePayload(Convert.ToString(payloadRange.Text) ?? string.Empty);
    }

    private static string ReadOlePayload(dynamic inlineShape)
    {
        return DecodePayload(Convert.ToString(inlineShape.AlternativeText) ?? string.Empty);
    }

    private static string EncodePayload(string json)
    {
        return MetadataPayloadPrefix + Convert.ToBase64String(Encoding.UTF8.GetBytes(json));
    }

    private static string DecodePayload(string value)
    {
        string normalized = value.TrimEnd('\r', '\a');
        if (!normalized.StartsWith(MetadataPayloadPrefix, StringComparison.Ordinal))
        {
            throw MetadataMissing();
        }

        try
        {
            byte[] bytes = Convert.FromBase64String(normalized.Substring(MetadataPayloadPrefix.Length));
            return Encoding.UTF8.GetString(bytes);
        }
        catch (FormatException exc)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"), exc);
        }
    }

    private static MetadataRecord DeserializeRecord(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            throw MetadataMissing();
        }

        var serializer = new JavaScriptSerializer();
        var dto = serializer.Deserialize<Dictionary<string, object>>(json);
        int schemaVersion = ReadInt(dto, "schemaVersion");
        if (schemaVersion != FormulaMetadata.CurrentSchemaVersion)
        {
            throw MetadataMissing();
        }

        var metadata = new FormulaMetadata(
            new FormulaIdentity(ReadRequiredString(dto, "documentId"), ReadRequiredString(dto, "equationId")),
            ReadString(dto, "latex"),
            ReadEnum<FormulaDisplayMode>(dto, "displayMode"),
            ReadEnum<NumberingMode>(dto, "numberingMode"),
            ReadString(dto, "numberText"),
            ReadEnum<RenderEngineKind>(dto, "renderEngine"),
            schemaVersion,
            ReadRequiredDouble(dto, "fontScale"));
        return new MetadataRecord(
            metadata,
            ReadDouble(dto, "naturalWidthPoints"),
            ReadDouble(dto, "naturalHeightPoints"),
            ReadDouble(dto, "naturalFontSizePoints"));
    }

    private static void ValidateMetadata(FormulaMetadata metadata, RenderEngineKind renderEngine)
    {
        if (metadata == null
            || metadata.SchemaVersion != FormulaMetadata.CurrentSchemaVersion
            || metadata.RenderEngine != renderEngine)
        {
            throw MetadataMissing();
        }
    }

    private static void ValidateStoredRecord(MetadataRecord record, RenderEngineKind renderEngine)
    {
        ValidateMetadata(record.Metadata, renderEngine);
        bool validDimensions = renderEngine == RenderEngineKind.Omml
            ? record.NaturalFontSizePoints > 0
            : record.NaturalWidthPoints > 0 && record.NaturalHeightPoints > 0;
        if (!validDimensions)
        {
            throw MetadataMissing();
        }
    }

    private static void ValidateDocumentIdentity(dynamic document, FormulaMetadata metadata)
    {
        if (!string.Equals(
            WordDocumentIdentityStore.GetOrCreate(document),
            metadata.Identity.DocumentId,
            StringComparison.Ordinal))
        {
            throw MetadataMissing();
        }
    }

    private static void ValidateStoredIdentity(string? tag, MetadataRecord record)
    {
        if (!string.Equals(
            EquationIdFromTag(tag ?? string.Empty),
            record.Metadata.Identity.EquationId,
            StringComparison.Ordinal))
        {
            throw MetadataMissing();
        }
    }

    private static string ReadString(Dictionary<string, object> dto, string key)
    {
        if (!dto.TryGetValue(key, out object value))
        {
            throw MetadataMissing();
        }

        return Convert.ToString(value) ?? string.Empty;
    }

    private static string ReadRequiredString(Dictionary<string, object> dto, string key)
    {
        string value = ReadString(dto, key);
        if (string.IsNullOrWhiteSpace(value))
        {
            throw MetadataMissing();
        }

        return value;
    }

    private static int ReadInt(Dictionary<string, object> dto, string key)
    {
        if (!dto.TryGetValue(key, out object value)
            || !int.TryParse(Convert.ToString(value), out int parsed))
        {
            throw MetadataMissing();
        }

        return parsed;
    }

    private static double ReadDouble(Dictionary<string, object> dto, string key)
    {
        return dto.TryGetValue(key, out object value)
            && double.TryParse(
                Convert.ToString(value),
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture,
                out double parsed)
            ? parsed
            : 0;
    }

    private static double ReadRequiredDouble(Dictionary<string, object> dto, string key)
    {
        double value = ReadDouble(dto, key);
        if (value <= 0)
        {
            throw MetadataMissing();
        }

        return value;
    }

    private static TEnum ReadEnum<TEnum>(Dictionary<string, object> dto, string key)
        where TEnum : struct
    {
        if (!dto.TryGetValue(key, out object value)
            || !Enum.TryParse(Convert.ToString(value), ignoreCase: true, out TEnum parsed))
        {
            throw MetadataMissing();
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

    private static InvalidOperationException MetadataMissing()
    {
        return new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
    }

    private sealed class MetadataRecord
    {
        public MetadataRecord(
            FormulaMetadata metadata,
            double naturalWidthPoints,
            double naturalHeightPoints,
            double naturalFontSizePoints)
        {
            Metadata = metadata;
            NaturalWidthPoints = naturalWidthPoints;
            NaturalHeightPoints = naturalHeightPoints;
            NaturalFontSizePoints = naturalFontSizePoints;
        }

        public FormulaMetadata Metadata { get; }

        public double NaturalWidthPoints { get; }

        public double NaturalHeightPoints { get; }

        public double NaturalFontSizePoints { get; }
    }
}
