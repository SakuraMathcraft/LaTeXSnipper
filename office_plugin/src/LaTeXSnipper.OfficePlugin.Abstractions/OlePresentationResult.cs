using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class OlePresentationResult
{
    public OlePresentationResult(
        OlePresentationKind presentationKind,
        string mimeType,
        byte[] payload,
        double widthPoints,
        double heightPoints,
        double baselinePoints)
    {
        PresentationKind = presentationKind;
        MimeType = mimeType ?? throw new ArgumentNullException(nameof(mimeType));
        Payload = payload ?? throw new ArgumentNullException(nameof(payload));
        WidthPoints = widthPoints;
        HeightPoints = heightPoints;
        BaselinePoints = baselinePoints;
    }

    public OlePresentationKind PresentationKind { get; }

    public string MimeType { get; }

    public byte[] Payload { get; }

    public double WidthPoints { get; }

    public double HeightPoints { get; }

    public double BaselinePoints { get; }
}
