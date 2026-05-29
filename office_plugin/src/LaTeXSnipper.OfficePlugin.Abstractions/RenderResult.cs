using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>
/// Renderer output. Payload is encoded by MIME type so Office adapters can stay engine-neutral.
/// </summary>
public sealed class RenderResult
{
    public RenderResult(RenderEngineKind engine, string mimeType, byte[] payload, double widthPoints, double heightPoints)
    {
        Engine = engine;
        MimeType = mimeType ?? throw new ArgumentNullException(nameof(mimeType));
        Payload = payload ?? throw new ArgumentNullException(nameof(payload));
        WidthPoints = widthPoints;
        HeightPoints = heightPoints;
    }

    public RenderEngineKind Engine { get; }

    public string MimeType { get; }

    public byte[] Payload { get; }

    public double WidthPoints { get; }

    public double HeightPoints { get; }
}
