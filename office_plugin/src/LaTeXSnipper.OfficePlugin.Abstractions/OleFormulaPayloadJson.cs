using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public static class OleFormulaPayloadJson
{
    public static string Serialize(FormulaMetadata metadata, OlePresentationResult presentation)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (presentation == null)
        {
            throw new ArgumentNullException(nameof(presentation));
        }

        var dto = new Dictionary<string, object?>
        {
            ["schemaVersion"] = OleFormulaPayload.CurrentSchemaVersion,
            ["documentId"] = metadata.Identity.DocumentId,
            ["equationId"] = metadata.Identity.EquationId,
            ["latex"] = metadata.Latex,
            ["displayMode"] = metadata.DisplayMode.ToString(),
            ["numberingMode"] = metadata.NumberingMode.ToString(),
            ["numberText"] = metadata.NumberText,
            ["fontColor"] = metadata.FontColor,
            ["fontStyle"] = metadata.FontStyle,
            ["fontScale"] = metadata.FontScale.ToString(CultureInfo.InvariantCulture),
            ["renderEngine"] = RenderEngineKind.MathJaxSvg.ToString(),
            ["rendererVersion"] = "MathJax-3.2.2",
            ["widthPoints"] = presentation.WidthPoints.ToString(CultureInfo.InvariantCulture),
            ["heightPoints"] = presentation.HeightPoints.ToString(CultureInfo.InvariantCulture),
            ["baselinePoints"] = presentation.BaselinePoints.ToString(CultureInfo.InvariantCulture),
            ["presentationKind"] = presentation.PresentationKind.ToString(),
            ["presentationMimeType"] = presentation.MimeType,
            ["presentationPayloadBase64"] = Convert.ToBase64String(presentation.Payload)
        };
        var builder = new StringBuilder();
        builder.Append('{');
        bool first = true;
        foreach (KeyValuePair<string, object?> item in dto)
        {
            if (!first)
            {
                builder.Append(',');
            }

            first = false;
            builder.Append('"').Append(Escape(item.Key)).Append('"').Append(':');
            builder.Append('"').Append(Escape(Convert.ToString(item.Value, CultureInfo.InvariantCulture) ?? string.Empty)).Append('"');
        }

        builder.Append('}');
        return builder.ToString();
    }

    private static string Escape(string value)
    {
        return value
            .Replace("\\", "\\\\")
            .Replace("\"", "\\\"")
            .Replace("\r", "\\r")
            .Replace("\n", "\\n")
            .Replace("\t", "\\t");
    }
}
