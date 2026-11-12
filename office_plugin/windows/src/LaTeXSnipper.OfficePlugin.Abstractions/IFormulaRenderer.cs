using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public interface IFormulaRenderer
{
    RenderEngineKind Engine { get; }

    Task<RenderResult> RenderAsync(RenderRequest request, CancellationToken cancellationToken);
}
