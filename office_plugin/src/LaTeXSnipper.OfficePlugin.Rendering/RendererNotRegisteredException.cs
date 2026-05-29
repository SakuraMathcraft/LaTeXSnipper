using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class RendererNotRegisteredException : InvalidOperationException
{
    public RendererNotRegisteredException(RenderEngineKind engine)
        : base("No formula renderer is registered for " + engine + ".")
    {
        Engine = engine;
    }

    public RenderEngineKind Engine { get; }
}
