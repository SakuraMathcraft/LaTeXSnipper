using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public interface IOfficeEquationHost
{
    OfficeHostKind HostKind { get; }

    Task<FormulaMetadata?> LoadSelectedAsync(CancellationToken cancellationToken);

    Task InsertAsync(FormulaMetadata metadata, RenderResult renderResult, CancellationToken cancellationToken);

    Task UpdateSelectedAsync(FormulaMetadata metadata, RenderResult renderResult, CancellationToken cancellationToken);

    Task DeleteSelectedAsync(CancellationToken cancellationToken);

    Task<int> RenumberAllAsync(CancellationToken cancellationToken);
}
