using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class FormulaRenderPipeline
{
    private readonly Dictionary<RenderEngineKind, IFormulaRenderer> _renderers = new Dictionary<RenderEngineKind, IFormulaRenderer>();

    public FormulaRenderPipeline(IEnumerable<IFormulaRenderer> renderers)
    {
        if (renderers == null)
        {
            throw new ArgumentNullException(nameof(renderers));
        }

        foreach (IFormulaRenderer renderer in renderers)
        {
            _renderers[renderer.Engine] = renderer;
        }
    }

    public Task<RenderResult> RenderAsync(RenderRequest request, CancellationToken cancellationToken)
    {
        if (request == null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (!_renderers.TryGetValue(request.Engine, out IFormulaRenderer? renderer))
        {
            throw new RendererNotRegisteredException(request.Engine);
        }

        return renderer.RenderAsync(request, cancellationToken);
    }
}
