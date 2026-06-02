using System;
using System.Collections.Generic;
using System.Globalization;
#if NET48
using System.Web.Script.Serialization;
#else
using System.Text.Json;
#endif

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal sealed class MathJaxSvgRenderResponse
{
    private const double ExToPoints = 4.5;

    private MathJaxSvgRenderResponse(
        string svg,
        double widthPoints,
        double heightPoints,
        double baselinePoints,
        string rendererVersion,
        IReadOnlyList<string> warnings)
    {
        Svg = svg;
        WidthPoints = widthPoints;
        HeightPoints = heightPoints;
        BaselinePoints = baselinePoints;
        RendererVersion = rendererVersion;
        Warnings = warnings;
    }

    public string Svg { get; }

    public double WidthPoints { get; }

    public double HeightPoints { get; }

    public double BaselinePoints { get; }

    public string RendererVersion { get; }

    public IReadOnlyList<string> Warnings { get; }

    public static MathJaxSvgRenderResponse Parse(string responseJson)
    {
#if NET48
        var serializer = new JavaScriptSerializer();
        object parsed = serializer.DeserializeObject(responseJson);
        if (parsed is string nested)
        {
            parsed = serializer.DeserializeObject(nested);
        }

        if (parsed is not Dictionary<string, object> root)
        {
            throw new InvalidOperationException("MathJax returned an invalid render response.");
        }

        return ParseObject(root);
#else
        using JsonDocument document = JsonDocument.Parse(responseJson);
        JsonElement root = document.RootElement;
        if (root.ValueKind == JsonValueKind.String)
        {
            string nested = root.GetString() ?? "{}";
            using JsonDocument nestedDocument = JsonDocument.Parse(nested);
            return ParseObject(nestedDocument.RootElement);
        }

        return ParseObject(root);
#endif
    }

#if NET48
    private static MathJaxSvgRenderResponse ParseObject(Dictionary<string, object> root)
    {
        string svg = GetString(root, "svg");
        if (string.IsNullOrWhiteSpace(svg))
        {
            throw new InvalidOperationException("MathJax returned an empty SVG payload.");
        }

        double scale = ReadScale(root);
        double widthPoints = CssLengthToPoints(GetString(root, "widthEx")) * scale;
        double heightPoints = CssLengthToPoints(GetString(root, "heightEx")) * scale;
        double baselinePoints = ExtractVerticalAlignPoints(GetString(root, "style")) * scale;
        string version = GetString(root, "version");
        return new MathJaxSvgRenderResponse(svg, widthPoints, heightPoints, baselinePoints, version, GetWarnings(root));
    }

    private static string GetString(Dictionary<string, object> root, string propertyName)
    {
        return root.TryGetValue(propertyName, out object value) ? Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty : string.Empty;
    }

    private static IReadOnlyList<string> GetWarnings(Dictionary<string, object> root)
    {
        if (!root.TryGetValue("warnings", out object warningsObject) || warningsObject is not object[] warningsArray)
        {
            return Array.Empty<string>();
        }

        var warnings = new List<string>();
        foreach (object warning in warningsArray)
        {
            string text = Convert.ToString(warning, CultureInfo.InvariantCulture) ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(text))
            {
                warnings.Add(text);
            }
        }

        return warnings;
    }

    private static double ReadScale(Dictionary<string, object> root)
    {
        if (!root.TryGetValue("scale", out object value))
        {
            return 1;
        }

        return double.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Float, CultureInfo.InvariantCulture, out double scale) && scale > 0
            ? scale
            : 1;
    }
#else
    private static MathJaxSvgRenderResponse ParseObject(JsonElement root)
    {
        string svg = GetString(root, "svg");
        if (string.IsNullOrWhiteSpace(svg))
        {
            throw new InvalidOperationException("MathJax returned an empty SVG payload.");
        }

        double scale = ReadScale(root);
        double widthPoints = CssLengthToPoints(GetString(root, "widthEx")) * scale;
        double heightPoints = CssLengthToPoints(GetString(root, "heightEx")) * scale;
        double baselinePoints = ExtractVerticalAlignPoints(GetString(root, "style")) * scale;
        string version = GetString(root, "version");
        return new MathJaxSvgRenderResponse(svg, widthPoints, heightPoints, baselinePoints, version, GetWarnings(root));
    }

    private static string GetString(JsonElement root, string propertyName)
    {
        return root.TryGetProperty(propertyName, out JsonElement value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : string.Empty;
    }

    private static IReadOnlyList<string> GetWarnings(JsonElement root)
    {
        if (!root.TryGetProperty("warnings", out JsonElement warningsElement) || warningsElement.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        var warnings = new List<string>();
        foreach (JsonElement warning in warningsElement.EnumerateArray())
        {
            if (warning.ValueKind == JsonValueKind.String)
            {
                string? text = warning.GetString();
                if (!string.IsNullOrWhiteSpace(text))
                {
                    warnings.Add(text);
                }
            }
        }

        return warnings;
    }

    private static double ReadScale(JsonElement root)
    {
        if (!root.TryGetProperty("scale", out JsonElement value))
        {
            return 1;
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out double number) && number > 0)
        {
            return number;
        }

        return 1;
    }
#endif

    private static double CssLengthToPoints(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return 0;
        }

        string trimmed = value.Trim();
        if (trimmed.EndsWith("ex", StringComparison.OrdinalIgnoreCase))
        {
            return ParseNumber(trimmed.Substring(0, trimmed.Length - 2)) * ExToPoints;
        }

        if (trimmed.EndsWith("em", StringComparison.OrdinalIgnoreCase))
        {
            return ParseNumber(trimmed.Substring(0, trimmed.Length - 2)) * 10.5;
        }

        if (trimmed.EndsWith("pt", StringComparison.OrdinalIgnoreCase))
        {
            return ParseNumber(trimmed.Substring(0, trimmed.Length - 2));
        }

        return ParseNumber(trimmed);
    }

    private static double ExtractVerticalAlignPoints(string style)
    {
        const string prefix = "vertical-align:";
        if (string.IsNullOrWhiteSpace(style))
        {
            return 0;
        }

        int start = style.IndexOf(prefix, StringComparison.OrdinalIgnoreCase);
        if (start < 0)
        {
            return 0;
        }

        start += prefix.Length;
        int end = style.IndexOf(';', start);
        string value = end >= 0 ? style.Substring(start, end - start) : style.Substring(start);
        return Math.Abs(CssLengthToPoints(value));
    }

    private static double ParseNumber(string value)
    {
        return double.TryParse(value.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out double result)
            ? result
            : 0;
    }
}
