using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class OlePresentationRequest
{
    public OlePresentationRequest(RenderResult intermediateRender, OlePresentationKind presentationKind)
    {
        IntermediateRender = intermediateRender ?? throw new ArgumentNullException(nameof(intermediateRender));
        PresentationKind = presentationKind;
    }

    public RenderResult IntermediateRender { get; }

    public OlePresentationKind PresentationKind { get; }

    public string Theme { get; set; } = "light";

    public TimeSpan Timeout { get; set; } = OfficeCommandTimeouts.Render;
}
