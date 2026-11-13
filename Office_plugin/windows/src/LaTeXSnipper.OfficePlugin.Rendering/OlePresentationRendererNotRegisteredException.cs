using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class OlePresentationRendererNotRegisteredException : InvalidOperationException
{
    public OlePresentationRendererNotRegisteredException(OlePresentationKind presentationKind)
        : base("No OLE presentation renderer is registered for " + presentationKind + ".")
    {
        PresentationKind = presentationKind;
    }

    public OlePresentationKind PresentationKind { get; }
}
