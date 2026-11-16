namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointRenderedImage
{
    public PowerPointRenderedImage(string path, float widthPoints, float heightPoints)
    {
        Path = path ?? string.Empty;
        WidthPoints = widthPoints;
        HeightPoints = heightPoints;
    }

    public string Path { get; }

    public float WidthPoints { get; }

    public float HeightPoints { get; }
}
