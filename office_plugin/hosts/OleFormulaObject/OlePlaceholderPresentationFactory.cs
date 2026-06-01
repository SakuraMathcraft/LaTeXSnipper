using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class OlePlaceholderPresentationFactory
{
    private const double WidthPoints = 180;
    private const double HeightPoints = 42;
    private const double BaselinePoints = 28;

    public static OleFormulaPresentation CreateDefault()
    {
        var identity = new FormulaIdentity("ole-object", Guid.NewGuid().ToString("N"));
        var payload = new OleFormulaPayload(
            identity,
            OleFormulaPresentationFactory.DefaultLatex,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            "placeholder",
            WidthPoints,
            HeightPoints,
            BaselinePoints);
        return new OleFormulaPresentation(payload, CreatePlaceholderEmf(payload.Latex));
    }

    private static byte[] CreatePlaceholderEmf(string latex)
    {
        int widthPixels = PointsToPixels(WidthPoints);
        int heightPixels = PointsToPixels(HeightPoints);
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
            using (var borderPen = new Pen(Color.FromArgb(80, 80, 80), 2))
            using (var textBrush = new SolidBrush(Color.Black))
            using (var captionBrush = new SolidBrush(Color.FromArgb(90, 90, 90)))
            using (var captionFont = new Font("Segoe UI", 8f, FontStyle.Regular, GraphicsUnit.Point))
            using (var formulaFont = new Font("Cambria Math", 16f, FontStyle.Regular, GraphicsUnit.Point))
            {
                graphics.SmoothingMode = SmoothingMode.AntiAlias;
                graphics.Clear(Color.Transparent);
                graphics.DrawRectangle(borderPen, 1, 1, widthPixels - 3, heightPixels - 3);
                graphics.DrawString("LaTeXSnipper Formula", captionFont, captionBrush, new PointF(8, 5));
                graphics.DrawString(latex, formulaFont, textBrush, new PointF(8, 18));
            }

            return stream.ToArray();
        }
        finally
        {
            referenceGraphics.ReleaseHdc(hdc);
        }
    }

    private static int PointsToPixels(double points)
    {
        return (int)Math.Ceiling(points / 72d * 300d);
    }
}
