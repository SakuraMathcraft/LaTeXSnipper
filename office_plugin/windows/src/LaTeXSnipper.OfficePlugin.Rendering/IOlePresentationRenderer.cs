using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public interface IOlePresentationRenderer
{
    OlePresentationKind PresentationKind { get; }

    Task<OlePresentationResult> RenderPresentationAsync(OlePresentationRequest request, CancellationToken cancellationToken);
}
