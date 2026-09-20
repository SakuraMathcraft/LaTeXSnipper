using System;
using System.Globalization;
using System.Text;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointFormulaMetadataStore
{
    public const string EquationIdTag = "LaTeXSnipperEquationId";
    public const string DocumentIdTag = "LaTeXSnipperDocumentId";
    public const string LatexChunkCountTag = "LaTeXSnipperLatexChunks";
    public const string LatexByteLengthTag = "LaTeXSnipperLatexBytes";
    public const string DisplayModeTag = "LaTeXSnipperDisplayMode";
    public const string SchemaVersionTag = "LaTeXSnipperSchemaVersion";
    public const string RenderEngineTag = "LaTeXSnipperRenderEngine";
    private const string TypographyPrefix = "LaTeXSnipperTypography";
    public const string NaturalWidthPointsTag = "LaTeXSnipperNaturalWidthPoints";
    public const string NaturalHeightPointsTag = "LaTeXSnipperNaturalHeightPoints";
    public const string ImagePathTag = "LaTeXSnipperImagePath";
    private const string LatexChunkTagPrefix = "LaTeXSnipperLatex";
    private const int TagChunkLength = 200;
    private const int MaxLatexChunkCount = 10000;

    public static void ApplyToShape(dynamic shape, FormulaMetadata metadata, float naturalWidthPoints, float naturalHeightPoints)
    {
        if (shape == null)
        {
            throw new ArgumentNullException(nameof(shape));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (metadata.SchemaVersion != FormulaMetadata.CurrentSchemaVersion)
        {
            throw MetadataMissing();
        }

        shape.AlternativeText = "LaTeXSnipper formula " + metadata.Identity.EquationId;
        ApplyMetadataTags(shape, metadata);
        shape.Tags.Add(NaturalWidthPointsTag, naturalWidthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(NaturalHeightPointsTag, naturalHeightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private static void ApplyMetadataTags(dynamic shape, FormulaMetadata metadata)
    {
        shape.Tags.Add(DocumentIdTag, metadata.Identity.DocumentId);
        shape.Tags.Add(EquationIdTag, metadata.Identity.EquationId);
        WriteEncodedText(shape, metadata.Latex);
        shape.Tags.Add(DisplayModeTag, metadata.DisplayMode.ToString());
        shape.Tags.Add(SchemaVersionTag, metadata.SchemaVersion.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(RenderEngineTag, metadata.RenderEngine.ToString());
        WriteEncodedText(shape, new JavaScriptSerializer().Serialize(FormulaTypographyFields.Write(metadata.Typography)), TypographyPrefix);
    }

    public static FormulaMetadata LoadFromShape(dynamic shape)
    {
        try { return LoadFromShapeCore(shape); }
        catch (Exception error) when (error is ArgumentException || error is FormatException
            || error is InvalidCastException || error is KeyNotFoundException || error is NullReferenceException)
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaMetadataMissing"), error);
        }
    }

    private static FormulaMetadata LoadFromShapeCore(dynamic shape)
    {
        string equationId = ReadRequiredTag(shape, EquationIdTag);
        int schemaVersion = ReadRequiredIntTag(shape, SchemaVersionTag);
        if (schemaVersion != FormulaMetadata.CurrentSchemaVersion)
        {
            throw MetadataMissing();
        }

        return new FormulaMetadata(
            new FormulaIdentity(ReadRequiredTag(shape, DocumentIdTag), equationId),
            ReadEncodedText(shape),
            ReadRequiredEnumTag<FormulaDisplayMode>(shape, DisplayModeTag),
            NumberingMode.None,
            string.Empty,
            ReadRequiredEnumTag<RenderEngineKind>(shape, RenderEngineTag),
            FormulaMetadata.CurrentSchemaVersion,
            FormulaTypographyFields.Read(new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(ReadEncodedText(shape, TypographyPrefix))));
    }

    private static void WriteEncodedText(dynamic shape, string value, string prefix = LatexChunkTagPrefix)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(value ?? string.Empty);
        var encoded = new StringBuilder(bytes.Length * 2);
        foreach (byte valueByte in bytes)
        {
            encoded.Append(valueByte.ToString("X2", CultureInfo.InvariantCulture));
        }

        string payload = encoded.Length == 0 ? "0" : encoded.ToString();
        int chunkCount = (payload.Length + TagChunkLength - 1) / TagChunkLength;
        shape.Tags.Add(prefix + "Bytes", bytes.Length.ToString(CultureInfo.InvariantCulture));
        shape.Tags.Add(prefix + "Chunks", chunkCount.ToString(CultureInfo.InvariantCulture));
        for (int index = 0; index < chunkCount; index++)
        {
            int start = index * TagChunkLength;
            int length = Math.Min(TagChunkLength, payload.Length - start);
            shape.Tags.Add(BuildChunkTag(prefix, index), payload.Substring(start, length));
        }
    }

    private static string ReadEncodedText(dynamic shape, string prefix = LatexChunkTagPrefix)
    {
        int byteLength = ReadRequiredIntTag(shape, prefix + "Bytes");
        int chunkCount = ReadRequiredIntTag(shape, prefix + "Chunks");
        if (byteLength < 0 || chunkCount <= 0 || chunkCount > MaxLatexChunkCount)
        {
            throw MetadataMissing();
        }

        var encoded = new StringBuilder(chunkCount * TagChunkLength);
        for (int index = 0; index < chunkCount; index++)
        {
            encoded.Append(ReadRequiredTag(shape, BuildChunkTag(prefix, index)));
        }

        if (byteLength == 0)
        {
            return encoded.ToString() == "0" ? string.Empty : throw MetadataMissing();
        }

        if (encoded.Length % 2 != 0)
        {
            throw MetadataMissing();
        }

        byte[] bytes = new byte[encoded.Length / 2];
        if (bytes.Length != byteLength)
        {
            throw MetadataMissing();
        }
        for (int index = 0; index < bytes.Length; index++)
        {
            if (!byte.TryParse(
                    encoded.ToString(index * 2, 2),
                    NumberStyles.HexNumber,
                    CultureInfo.InvariantCulture,
                    out bytes[index]))
            {
                throw MetadataMissing();
            }
        }

        return Encoding.UTF8.GetString(bytes);
    }

    private static string BuildChunkTag(string prefix, int index)
    {
        return prefix + index.ToString("D4", CultureInfo.InvariantCulture);
    }

    private static string ReadRequiredTag(dynamic shape, string name)
    {
        try
        {
            string value = Convert.ToString(shape.Tags[name]) ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(value))
            {
                return value;
            }
        }
        catch
        {
        }

        throw MetadataMissing();
    }

    private static int ReadRequiredIntTag(dynamic shape, string name)
    {
        if (int.TryParse(ReadRequiredTag(shape, name), NumberStyles.Integer, CultureInfo.InvariantCulture, out int value))
        {
            return value;
        }

        throw MetadataMissing();
    }

    private static TEnum ReadRequiredEnumTag<TEnum>(dynamic shape, string name)
        where TEnum : struct
    {
        if (Enum.TryParse(ReadRequiredTag(shape, name), true, out TEnum value))
        {
            return value;
        }

        throw MetadataMissing();
    }

    private static InvalidOperationException MetadataMissing()
    {
        return new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaMetadataMissing"));
    }

    public static void ApplyImagePath(dynamic shape, string imagePath)
    {
        if (shape == null)
        {
            throw new ArgumentNullException(nameof(shape));
        }

        shape.Tags.Add(ImagePathTag, imagePath ?? string.Empty);
    }
}
