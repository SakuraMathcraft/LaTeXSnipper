using System;
using System.Globalization;
using System.Text;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointFormulaMetadataStore
{
    public const string EquationIdTag = "LaTeXSnipperEquationId";
    public const string LatexChunkCountTag = "LaTeXSnipperLatexChunks";
    public const string LatexByteLengthTag = "LaTeXSnipperLatexBytes";
    public const string DisplayModeTag = "LaTeXSnipperDisplayMode";
    public const string SchemaVersionTag = "LaTeXSnipperSchemaVersion";
    public const string RenderEngineTag = "LaTeXSnipperRenderEngine";
    public const string FontColorTag = "LaTeXSnipperFontColor";
    public const string FontStyleTag = "LaTeXSnipperFontStyle";
    public const string FontScaleTag = "LaTeXSnipperFontScale";
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

        shape.AlternativeText = "LaTeXSnipper formula " + metadata.Identity.EquationId;
        ApplyMetadataTags(shape, metadata);
        shape.Tags.Add(NaturalWidthPointsTag, naturalWidthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(NaturalHeightPointsTag, naturalHeightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private static void ApplyMetadataTags(dynamic shape, FormulaMetadata metadata)
    {
        shape.Tags.Add(EquationIdTag, metadata.Identity.EquationId);
        WriteEncodedText(shape, metadata.Latex);
        shape.Tags.Add(DisplayModeTag, metadata.DisplayMode.ToString());
        shape.Tags.Add(SchemaVersionTag, metadata.SchemaVersion.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(RenderEngineTag, metadata.RenderEngine.ToString());
        shape.Tags.Add(FontColorTag, metadata.FontColor);
        shape.Tags.Add(FontStyleTag, metadata.FontStyle.ToString());
        shape.Tags.Add(FontScaleTag, metadata.FontScale.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    public static FormulaMetadata LoadFromShape(dynamic shape)
    {
        string equationId = ReadRequiredTag(shape, EquationIdTag);

        return new FormulaMetadata(
            new FormulaIdentity("active-presentation", equationId),
            ReadEncodedText(shape),
            ReadRequiredEnumTag<FormulaDisplayMode>(shape, DisplayModeTag),
            NumberingMode.None,
            string.Empty,
            ReadRequiredEnumTag<RenderEngineKind>(shape, RenderEngineTag),
            ReadRequiredIntTag(shape, SchemaVersionTag),
            ReadRequiredTag(shape, FontColorTag),
            ReadRequiredEnumTag<FormulaFontStyle>(shape, FontStyleTag),
            ReadRequiredDoubleTag(shape, FontScaleTag));
    }

    private static void WriteEncodedText(dynamic shape, string value)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(value ?? string.Empty);
        var encoded = new StringBuilder(bytes.Length * 2);
        foreach (byte valueByte in bytes)
        {
            encoded.Append(valueByte.ToString("X2", CultureInfo.InvariantCulture));
        }

        string payload = encoded.Length == 0 ? "0" : encoded.ToString();
        int chunkCount = (payload.Length + TagChunkLength - 1) / TagChunkLength;
        shape.Tags.Add(LatexByteLengthTag, bytes.Length.ToString(CultureInfo.InvariantCulture));
        shape.Tags.Add(LatexChunkCountTag, chunkCount.ToString(CultureInfo.InvariantCulture));
        for (int index = 0; index < chunkCount; index++)
        {
            int start = index * TagChunkLength;
            int length = Math.Min(TagChunkLength, payload.Length - start);
            shape.Tags.Add(BuildLatexChunkTag(index), payload.Substring(start, length));
        }
    }

    private static string ReadEncodedText(dynamic shape)
    {
        int byteLength = ReadRequiredIntTag(shape, LatexByteLengthTag);
        int chunkCount = ReadRequiredIntTag(shape, LatexChunkCountTag);
        if (byteLength < 0 || chunkCount <= 0 || chunkCount > MaxLatexChunkCount)
        {
            throw MetadataMissing();
        }

        var encoded = new StringBuilder(chunkCount * TagChunkLength);
        for (int index = 0; index < chunkCount; index++)
        {
            encoded.Append(ReadRequiredTag(shape, BuildLatexChunkTag(index)));
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

    private static string BuildLatexChunkTag(int index)
    {
        return LatexChunkTagPrefix + index.ToString("D4", CultureInfo.InvariantCulture);
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

    private static double ReadRequiredDoubleTag(dynamic shape, string name)
    {
        if (double.TryParse(
                ReadRequiredTag(shape, name),
                NumberStyles.Float,
                CultureInfo.InvariantCulture,
                out double value) &&
            value > 0)
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
