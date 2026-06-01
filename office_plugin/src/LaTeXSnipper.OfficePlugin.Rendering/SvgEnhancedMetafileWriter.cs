#if NET48
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class SvgEnhancedMetafileWriter
{
    private const int Dpi = 600;

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

        using var referenceBitmap = new Bitmap(1, 1);
        using Graphics referenceGraphics = Graphics.FromImage(referenceBitmap);
        IntPtr hdc = referenceGraphics.GetHdc();
        try
        {
            using var stream = new MemoryStream();
            using (var metafile = new Metafile(
                stream,
                hdc,
                new RectangleF(0, 0, widthPixels, heightPixels),
                MetafileFrameUnit.Pixel,
                EmfType.EmfPlusDual))
            using (Graphics graphics = Graphics.FromImage(metafile))
            {
                graphics.SmoothingMode = SmoothingMode.AntiAlias;
                graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
                using var rootTransform = new Matrix();
                rootTransform.Scale(
                    widthPixels / Math.Max(1f, viewBox.Width),
                    heightPixels / Math.Max(1f, viewBox.Height),
                    MatrixOrder.Append);
                rootTransform.Translate(-viewBox.X, -viewBox.Y, MatrixOrder.Prepend);
                var paths = CollectPaths(root);
                DrawElement(root, graphics, paths, rootTransform, cancellationToken);
            }

            return stream.ToArray();
        }
        finally
        {
            referenceGraphics.ReleaseHdc(hdc);
        }
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
                transform.Multiply(local, MatrixOrder.Append);
            }
        }

        if (element.Name.LocalName == "use")
        {
            DrawUseElement(element, graphics, paths, transform);
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
        path.Transform(inheritedTransform);
        using var brush = new SolidBrush(Color.Black);
        graphics.FillPath(brush, path);
    }

    private static int PointsToPixels(double points)
    {
        return (int)Math.Ceiling(points / 72d * Dpi);
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

    internal static float ParseFloat(string value)
    {
        return float.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture);
    }
}
#endif
