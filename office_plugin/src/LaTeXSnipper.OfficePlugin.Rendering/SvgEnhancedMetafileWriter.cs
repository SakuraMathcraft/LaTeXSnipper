#if NET48
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class SvgEnhancedMetafileWriter
{
    private const int Dpi = 1200;
    private const int PointsPerInch = 72;

    public static byte[] Write(RenderResult intermediateRender, CancellationToken cancellationToken)
    {
        if (intermediateRender.MimeType != MathJaxSvgRenderer.SvgMimeType)
        {
            throw new ArgumentException("Enhanced Metafile presentation requires MathJax SVG intermediate render.", nameof(intermediateRender));
        }

        string svg = Encoding.UTF8.GetString(intermediateRender.Payload);
        var document = XDocument.Parse(svg);
        XElement root = document.Root ?? throw new InvalidOperationException("SVG root element was not found.");
        SvgViewBox viewBox = SvgViewBox.Parse(root.Attribute("viewBox")?.Value);
        int widthPixels = Math.Max(1, PointsToPixels(intermediateRender.WidthPoints));
        int heightPixels = Math.Max(1, PointsToPixels(intermediateRender.HeightPoints));

        using var stream = new MemoryStream();
        IntPtr screen = GetDC(IntPtr.Zero);
        if (screen == IntPtr.Zero)
        {
            throw new InvalidOperationException("Cannot acquire a screen device context for EMF rendering.");
        }

        try
        {
            using (var metafile = new Metafile(
                stream,
                screen,
                new RectangleF(0, 0, widthPixels, heightPixels),
                MetafileFrameUnit.Pixel,
                EmfType.EmfPlusDual,
                "LaTeXSnipper Formula"))
            {
                using Graphics graphics = Graphics.FromImage(metafile);
                ConfigureGraphics(graphics);
                using var rootTransform = new Matrix();
                rootTransform.Translate(-viewBox.X, -viewBox.Y, MatrixOrder.Append);
                rootTransform.Scale(
                    widthPixels / Math.Max(1f, viewBox.Width),
                    heightPixels / Math.Max(1f, viewBox.Height),
                    MatrixOrder.Append);
                DrawElement(root, graphics, CollectPaths(root), rootTransform, cancellationToken);
            }
        }
        finally
        {
            ReleaseDC(IntPtr.Zero, screen);
        }

        return stream.ToArray();
    }

    private static void ConfigureGraphics(Graphics graphics)
    {
        graphics.PageUnit = GraphicsUnit.Pixel;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
        graphics.CompositingQuality = CompositingQuality.HighQuality;
        graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
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

    private static void DrawElement(
        XElement element,
        Graphics graphics,
        IReadOnlyDictionary<string, GraphicsPath> paths,
        Matrix inheritedTransform,
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

        if (element.Name.LocalName == "use")
        {
            DrawUseElement(element, graphics, paths, transform);
        }
        else if (element.Name.LocalName == "rect")
        {
            DrawRectElement(element, graphics, transform);
        }

        foreach (XElement child in element.Elements())
        {
            DrawElement(child, graphics, paths, transform, cancellationToken);
        }
    }

    private static void DrawUseElement(
        XElement element,
        Graphics graphics,
        IReadOnlyDictionary<string, GraphicsPath> paths,
        Matrix inheritedTransform)
    {
        string href = element.Attribute(XName.Get("href", "http://www.w3.org/1999/xlink"))?.Value
            ?? element.Attribute("href")?.Value
            ?? string.Empty;
        if (!href.StartsWith("#", StringComparison.Ordinal) || !paths.TryGetValue(href.Substring(1), out GraphicsPath? sourcePath))
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
        graphics.FillPath(Brushes.Black, path);
    }

    private static void DrawRectElement(XElement element, Graphics graphics, Matrix inheritedTransform)
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
        graphics.FillPath(Brushes.Black, path);
    }

    private static int PointsToPixels(double points)
    {
        return (int)Math.Ceiling(points / PointsPerInch * Dpi);
    }

    internal static float ParseFloat(string value)
    {
        return float.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture);
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
                throw new InvalidOperationException("SVG viewBox is required for EMF presentation.");
            }

            return new SvgViewBox(ParseFloat(parts[0]), ParseFloat(parts[1]), ParseFloat(parts[2]), ParseFloat(parts[3]));
        }
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetDC(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);
}
#endif
