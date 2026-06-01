using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class OlePresentationPipeline
{
    private readonly Dictionary<OlePresentationKind, IOlePresentationRenderer> _renderers = new Dictionary<OlePresentationKind, IOlePresentationRenderer>();

    public OlePresentationPipeline(IEnumerable<IOlePresentationRenderer> renderers)
    {
        if (renderers == null)
        {
            throw new ArgumentNullException(nameof(renderers));
        }

        foreach (IOlePresentationRenderer renderer in renderers)
        {
            _renderers[renderer.PresentationKind] = renderer;
        }
    }

    public Task<OlePresentationResult> RenderAsync(OlePresentationRequest request, CancellationToken cancellationToken)
    {
        if (request == null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (!_renderers.TryGetValue(request.PresentationKind, out IOlePresentationRenderer? renderer))
        {
            throw new OlePresentationRendererNotRegisteredException(request.PresentationKind);
        }

        return renderer.RenderPresentationAsync(request, cancellationToken);
    }
}
