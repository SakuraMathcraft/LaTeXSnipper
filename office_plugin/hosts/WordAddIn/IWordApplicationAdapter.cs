using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public interface IWordApplicationAdapter
{
    Task InsertManagedEquationAsync(string ooxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken);

    Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken);

    Task UpdateSelectedFormulaAsync(string ooxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken);

    Task UpdateFormulaAsync(string equationId, string ooxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken);

    Task DeleteSelectedFormulaAsync(CancellationToken cancellationToken);

    Task<int> CountAutoNumberedFormulasAsync(CancellationToken cancellationToken);

    Task<int> RenumberAutomaticFormulasAsync(CancellationToken cancellationToken);

    Task<IReadOnlyList<FormulaMetadata>> LoadAllManagedFormulasAsync(CancellationToken cancellationToken);
}
