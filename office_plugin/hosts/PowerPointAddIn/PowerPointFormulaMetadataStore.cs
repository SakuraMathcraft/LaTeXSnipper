using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointFormulaMetadataStore
{
    public const string EquationIdTag = "LaTeXSnipperEquationId";
    public const string LatexTag = "LaTeXSnipperLatex";
    public const string DisplayModeTag = "LaTeXSnipperDisplayMode";
    public const string NumberingModeTag = "LaTeXSnipperNumberingMode";
    public const string NumberTextTag = "LaTeXSnipperNumberText";
    public const string SchemaVersionTag = "LaTeXSnipperSchemaVersion";

    public static void ApplyToShape(dynamic shape, FormulaMetadata metadata)
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
        shape.Tags.Add(EquationIdTag, metadata.Identity.EquationId);
        shape.Tags.Add(LatexTag, metadata.Latex);
        shape.Tags.Add(DisplayModeTag, metadata.DisplayMode.ToString());
        shape.Tags.Add(NumberingModeTag, metadata.NumberingMode.ToString());
        shape.Tags.Add(NumberTextTag, metadata.NumberText);
        shape.Tags.Add(SchemaVersionTag, metadata.SchemaVersion.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }
}
