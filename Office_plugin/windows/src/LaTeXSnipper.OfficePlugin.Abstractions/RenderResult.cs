using System;
using System.Collections.Generic;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>
/// Renderer output. Payload is encoded by MIME type so Office adapters can stay engine-neutral.
/// </summary>
public sealed class RenderResult
{
    public RenderResult(
        RenderEngineKind engine,
        string mimeType,
        byte[] payload,
        double widthPoints,
        double heightPoints,
        double baselinePoints = 0,
        string rendererVersion = "",
        IReadOnlyList<string>? warnings = null)
    {
        Engine = engine;
        MimeType = mimeType ?? throw new ArgumentNullException(nameof(mimeType));
        Payload = payload ?? throw new ArgumentNullException(nameof(payload));
        WidthPoints = widthPoints;
        HeightPoints = heightPoints;
        BaselinePoints = baselinePoints;
        RendererVersion = rendererVersion ?? string.Empty;
        Warnings = warnings ?? Array.Empty<string>();
    }

    public RenderEngineKind Engine { get; }

    public string MimeType { get; }

    public byte[] Payload { get; }

    public double WidthPoints { get; }

    public double HeightPoints { get; }

    public double BaselinePoints { get; }

    public string RendererVersion { get; }

    public IReadOnlyList<string> Warnings { get; }
}
