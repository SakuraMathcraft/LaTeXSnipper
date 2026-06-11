#if NET48
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public static class SvgPngRasterizer
{
    private const int DefaultDpi = 300;
    private const int PointsPerInch = 72;

    public static byte[] Rasterize(
        RenderResult svgRender,
        CancellationToken cancellationToken,
        int dpi = DefaultDpi)
    {
        if (dpi <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(dpi));
        }

        int width = Math.Max(1, (int)Math.Ceiling(svgRender.WidthPoints / PointsPerInch * dpi));
        int height = Math.Max(1, (int)Math.Ceiling(svgRender.HeightPoints / PointsPerInch * dpi));
        using var bitmap = new Bitmap(width, height, PixelFormat.Format32bppArgb);
        bitmap.SetResolution(dpi, dpi);
        using (Graphics graphics = Graphics.FromImage(bitmap))
        {
            graphics.Clear(Color.Transparent);
            graphics.SmoothingMode = SmoothingMode.AntiAlias;
            graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            graphics.CompositingQuality = CompositingQuality.HighQuality;
            SvgVectorGraphicsRenderer.Draw(svgRender, graphics, width, height, cancellationToken);
        }

        using var stream = new MemoryStream();
        bitmap.Save(stream, ImageFormat.Png);
        return stream.ToArray();
    }
}
#endif
