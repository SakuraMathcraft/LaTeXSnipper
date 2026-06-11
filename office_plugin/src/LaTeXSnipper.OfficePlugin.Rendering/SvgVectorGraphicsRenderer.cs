#if NET48
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.Text;
using System.Threading;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class SvgVectorGraphicsRenderer
{
    public static void Draw(
        RenderResult render,
        Graphics graphics,
        int widthPixels,
        int heightPixels,
        CancellationToken cancellationToken)
    {
        if (render.MimeType != MathJaxSvgRenderer.SvgMimeType)
        {
            throw new ArgumentException("MathJax SVG input is required.", nameof(render));
        }

        string svg = Encoding.UTF8.GetString(render.Payload);
        var document = XDocument.Parse(svg);
        XElement root = document.Root ?? throw new InvalidOperationException("SVG root element was not found.");
        SvgViewBox viewBox = SvgViewBox.Parse(root.Attribute("viewBox")?.Value);
        int weightPercent = ParseWeightPercent(root.Attribute("data-latexsnipper-weight")?.Value);
        float outlineWidth = weightPercent == 0
            ? 0
            : heightPixels * weightPercent / 1000f;
        using var rootTransform = new Matrix();
        rootTransform.Translate(-viewBox.X, -viewBox.Y, MatrixOrder.Append);
        rootTransform.Scale(
            widthPixels / Math.Max(1f, viewBox.Width),
            heightPixels / Math.Max(1f, viewBox.Height),
            MatrixOrder.Append);

        IReadOnlyDictionary<string, GraphicsPath> paths = CollectPaths(root);
        var paintBatches = new List<PaintBatch>();
        CollectGeometry(
            root,
            paths,
            rootTransform,
            Color.Black,
            Color.Black,
            clip: null,
            paintBatches,
            cancellationToken);
        foreach (PaintBatch batch in paintBatches)
        {
            GraphicsState state = graphics.Save();
            if (batch.Clip != null)
            {
                graphics.SetClip(batch.Clip, CombineMode.Intersect);
            }

            using var brush = new SolidBrush(batch.Color);
            graphics.FillPath(brush, batch.Path);
            if (outlineWidth > 0)
            {
                using var pen = new Pen(batch.Color, outlineWidth)
                {
                    LineJoin = LineJoin.Round,
                    StartCap = LineCap.Round,
                    EndCap = LineCap.Round
                };
                graphics.DrawPath(pen, batch.Path);
            }
            graphics.Restore(state);
            batch.Path.Dispose();
            batch.Clip?.Dispose();
        }

        foreach (GraphicsPath path in paths.Values)
        {
            path.Dispose();
        }
    }

    private static int ParseWeightPercent(string? value)
    {
        return int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsed)
            && parsed is 5 or 10 or 15
            ? parsed
            : 0;
    }

    private static Dictionary<string, GraphicsPath> CollectPaths(XElement root)
    {
        var paths = new Dictionary<string, GraphicsPath>(StringComparer.Ordinal);
        foreach (XElement pathElement in root.Descendants())
        {
            if (pathElement.Name.LocalName != "path")
            {
                continue;
            }

            string id = pathElement.Attribute("id")?.Value ?? string.Empty;
            string data = pathElement.Attribute("d")?.Value ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(id) && !string.IsNullOrWhiteSpace(data))
            {
                paths[id] = SvgPathDataParser.Parse(data);
            }
        }

        return paths;
    }

    private static void CollectGeometry(
        XElement element,
        IReadOnlyDictionary<string, GraphicsPath> paths,
        Matrix inheritedTransform,
        Color inheritedFill,
        Color inheritedCurrentColor,
        Region? clip,
        IList<PaintBatch> paintBatches,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        using Matrix transform = inheritedTransform.Clone();
        Matrix? local = SvgTransformParser.Parse(element.Attribute("transform")?.Value);
        if (local != null)
        {
            using (local)
            {
                transform.Multiply(local, MatrixOrder.Prepend);
            }
        }

        Region? childClip = clip;
        if (element.Name.LocalName == "svg" && element.Parent != null)
        {
            childClip = CreateNestedViewportClip(element, transform, clip);
            ApplyNestedViewport(element, transform);
        }

        Color currentColor = ResolvePaint(element, "color", inheritedCurrentColor, inheritedCurrentColor);
        Color fill = ResolvePaint(element, "fill", inheritedFill, currentColor);
        if (element.Name.LocalName == "use")
        {
            AddUseGeometry(element, paths, transform, fill, childClip, paintBatches);
        }
        else if (element.Name.LocalName == "rect")
        {
            AddRectGeometry(element, transform, fill, childClip, paintBatches);
        }
        else if (element.Name.LocalName == "text")
        {
            AddTextGeometry(element, transform, fill, childClip, paintBatches);
        }

        foreach (XElement child in element.Elements())
        {
            CollectGeometry(child, paths, transform, fill, currentColor, childClip, paintBatches, cancellationToken);
        }

        if (!ReferenceEquals(childClip, clip))
        {
            childClip?.Dispose();
        }
    }

    private static Region? CreateNestedViewportClip(XElement element, Matrix transform, Region? inheritedClip)
    {
        float width = ParseOptionalFloat(element.Attribute("width")?.Value);
        float height = ParseOptionalFloat(element.Attribute("height")?.Value);
        if (width <= 0 || height <= 0)
        {
            return inheritedClip;
        }

        float x = ParseOptionalFloat(element.Attribute("x")?.Value);
        float y = ParseOptionalFloat(element.Attribute("y")?.Value);
        using var viewportPath = new GraphicsPath(FillMode.Winding);
        viewportPath.AddRectangle(new RectangleF(x, y, width, height));
        viewportPath.Transform(transform);
        var clip = new Region(viewportPath);
        if (inheritedClip != null)
        {
            clip.Intersect(inheritedClip);
        }

        return clip;
    }

    private static void ApplyNestedViewport(XElement element, Matrix transform)
    {
        string? viewBoxValue = element.Attribute("viewBox")?.Value;
        if (string.IsNullOrWhiteSpace(viewBoxValue))
        {
            return;
        }

        SvgViewBox viewBox = SvgViewBox.Parse(viewBoxValue);
        float width = ParseOptionalFloat(element.Attribute("width")?.Value);
        float height = ParseOptionalFloat(element.Attribute("height")?.Value);
        if (width <= 0 || height <= 0 || viewBox.Width <= 0 || viewBox.Height <= 0)
        {
            return;
        }

        float x = ParseOptionalFloat(element.Attribute("x")?.Value);
        float y = ParseOptionalFloat(element.Attribute("y")?.Value);
        using var viewport = new Matrix();
        viewport.Translate(-viewBox.X, -viewBox.Y, MatrixOrder.Append);
        viewport.Scale(width / viewBox.Width, height / viewBox.Height, MatrixOrder.Append);
        viewport.Translate(x, y, MatrixOrder.Append);
        transform.Multiply(viewport, MatrixOrder.Prepend);
    }

    private static void AddUseGeometry(
        XElement element,
        IReadOnlyDictionary<string, GraphicsPath> paths,
        Matrix inheritedTransform,
        Color fill,
        Region? clip,
        IList<PaintBatch> paintBatches)
    {
        string href = element.Attribute(XName.Get("href", "http://www.w3.org/1999/xlink"))?.Value
            ?? element.Attribute("href")?.Value
            ?? string.Empty;
        if (!href.StartsWith("#", StringComparison.Ordinal) ||
            !paths.TryGetValue(href.Substring(1), out GraphicsPath? sourcePath))
        {
            return;
        }

        using GraphicsPath path = (GraphicsPath)sourcePath.Clone();
        using Matrix positionedTransform = inheritedTransform.Clone();
        float x = ParseOptionalFloat(element.Attribute("x")?.Value);
        float y = ParseOptionalFloat(element.Attribute("y")?.Value);
        if (x != 0 || y != 0)
        {
            using var translate = new Matrix();
            translate.Translate(x, y, MatrixOrder.Append);
            positionedTransform.Multiply(translate, MatrixOrder.Prepend);
        }

        path.Transform(positionedTransform);
        AddPaintGeometry(paintBatches, fill, clip, path);
    }

    private static void AddRectGeometry(
        XElement element,
        Matrix inheritedTransform,
        Color fill,
        Region? clip,
        IList<PaintBatch> paintBatches)
    {
        float x = ParseOptionalFloat(element.Attribute("x")?.Value);
        float y = ParseOptionalFloat(element.Attribute("y")?.Value);
        float width = ParseOptionalFloat(element.Attribute("width")?.Value);
        float height = ParseOptionalFloat(element.Attribute("height")?.Value);
        if (width <= 0 || height <= 0)
        {
            return;
        }

        using var path = new GraphicsPath(FillMode.Winding);
        path.AddRectangle(new RectangleF(x, y, width, height));
        path.Transform(inheritedTransform);
        AddPaintGeometry(paintBatches, fill, clip, path);
    }

    private static void AddTextGeometry(
        XElement element,
        Matrix inheritedTransform,
        Color fill,
        Region? clip,
        IList<PaintBatch> paintBatches)
    {
        string text = element.Value;
        if (string.IsNullOrEmpty(text))
        {
            return;
        }

        float fontSize = ParseOptionalFloat(
            element.Attribute("font-size")?.Value
            ?? ReadStyleProperty(element.Attribute("style")?.Value, "font-size"));
        if (fontSize <= 0)
        {
            fontSize = 1000;
        }

        float x = ParseOptionalFloat(element.Attribute("x")?.Value);
        float y = ParseOptionalFloat(element.Attribute("y")?.Value);
        using FontFamily fontFamily = ResolveFontFamily(
            element.Attribute("font-family")?.Value
            ?? ReadStyleProperty(element.Attribute("style")?.Value, "font-family"));
        int emHeight = fontFamily.GetEmHeight(FontStyle.Regular);
        int ascent = fontFamily.GetCellAscent(FontStyle.Regular);
        float top = y - (fontSize * ascent / emHeight);
        using var path = new GraphicsPath(FillMode.Winding);
        path.AddString(
            text,
            fontFamily,
            (int)FontStyle.Regular,
            fontSize,
            new PointF(x, top),
            StringFormat.GenericTypographic);
        path.Transform(inheritedTransform);
        AddPaintGeometry(paintBatches, fill, clip, path);
    }

    private static FontFamily ResolveFontFamily(string? requestedFamily)
    {
        string requested = (requestedFamily ?? string.Empty).Trim().Trim('"', '\'');
        if (!string.IsNullOrWhiteSpace(requested))
        {
            try
            {
                return new FontFamily(requested);
            }
            catch
            {
            }
        }

        foreach (string candidate in new[] { "Microsoft YaHei", "SimSun", "Segoe UI" })
        {
            try
            {
                return new FontFamily(candidate);
            }
            catch
            {
            }
        }

        return new FontFamily(FontFamily.GenericSansSerif.Name);
    }

    private static void AddPaintGeometry(
        IList<PaintBatch> batches,
        Color color,
        Region? clip,
        GraphicsPath geometry)
    {
        PaintBatch batch;
        if (batches.Count > 0 &&
            batches[batches.Count - 1].Color.ToArgb() == color.ToArgb() &&
            RegionsMatch(batches[batches.Count - 1].Clip, clip))
        {
            batch = batches[batches.Count - 1];
        }
        else
        {
            batch = new PaintBatch(color, clip);
            batches.Add(batch);
        }

        batch.Path.AddPath(geometry, connect: false);
    }

    private static bool RegionsMatch(Region? left, Region? right)
    {
        if (left == null || right == null)
        {
            return left == null && right == null;
        }

        using var identity = new Matrix();
        RectangleF[] leftScans = left.GetRegionScans(identity);
        RectangleF[] rightScans = right.GetRegionScans(identity);
        if (leftScans.Length != rightScans.Length)
        {
            return false;
        }

        for (int index = 0; index < leftScans.Length; index++)
        {
            if (leftScans[index] != rightScans[index])
            {
                return false;
            }
        }

        return true;
    }

    private static Color ResolvePaint(
        XElement element,
        string property,
        Color inherited,
        Color currentColor)
    {
        string value = element.Attribute(property)?.Value
            ?? ReadStyleProperty(element.Attribute("style")?.Value, property)
            ?? string.Empty;
        if (string.IsNullOrWhiteSpace(value))
        {
            return inherited;
        }

        string normalized = value.Trim();
        if (string.Equals(normalized, "currentColor", StringComparison.OrdinalIgnoreCase))
        {
            return currentColor;
        }

        if (string.Equals(normalized, "none", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(normalized, "transparent", StringComparison.OrdinalIgnoreCase))
        {
            return Color.Transparent;
        }

        try
        {
            return ColorTranslator.FromHtml(normalized);
        }
        catch
        {
            return inherited;
        }
    }

    private static string? ReadStyleProperty(string? style, string property)
    {
        if (string.IsNullOrWhiteSpace(style))
        {
            return null;
        }

        foreach (string declaration in style!.Split(';'))
        {
            int separator = declaration.IndexOf(':');
            if (separator <= 0)
            {
                continue;
            }

            if (string.Equals(declaration.Substring(0, separator).Trim(), property, StringComparison.OrdinalIgnoreCase))
            {
                return declaration.Substring(separator + 1).Trim();
            }
        }

        return null;
    }

    private static float ParseOptionalFloat(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return 0;
        }

        string trimmed = value!.Trim();
        if (trimmed.EndsWith("em", StringComparison.OrdinalIgnoreCase) ||
            trimmed.EndsWith("ex", StringComparison.OrdinalIgnoreCase) ||
            trimmed.EndsWith("pt", StringComparison.OrdinalIgnoreCase) ||
            trimmed.EndsWith("px", StringComparison.OrdinalIgnoreCase))
        {
            trimmed = trimmed.Substring(0, trimmed.Length - 2);
        }

        return float.TryParse(trimmed, NumberStyles.Float, CultureInfo.InvariantCulture, out float parsed)
            ? parsed
            : 0;
    }

    private readonly struct SvgViewBox
    {
        private SvgViewBox(float x, float y, float width, float height)
        {
            X = x;
            Y = y;
            Width = width;
            Height = height;
        }

        public float X { get; }
        public float Y { get; }
        public float Width { get; }
        public float Height { get; }

        public static SvgViewBox Parse(string? value)
        {
            string[] parts = (value ?? string.Empty).Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length != 4)
            {
                throw new InvalidOperationException("SVG viewBox is required.");
            }

            return new SvgViewBox(
                SvgEnhancedMetafileWriter.ParseFloat(parts[0]),
                SvgEnhancedMetafileWriter.ParseFloat(parts[1]),
                SvgEnhancedMetafileWriter.ParseFloat(parts[2]),
                SvgEnhancedMetafileWriter.ParseFloat(parts[3]));
        }
    }

    private sealed class PaintBatch
    {
        public PaintBatch(Color color, Region? clip)
        {
            Color = color;
            Clip = clip?.Clone();
            Path = new GraphicsPath(FillMode.Winding);
        }

        public Color Color { get; }

        public Region? Clip { get; }

        public GraphicsPath Path { get; }
    }
}
#endif
