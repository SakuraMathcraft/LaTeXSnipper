using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public interface IWordApplicationAdapter
{
    Task ValidateCurrentInsertionTargetAsync(CancellationToken cancellationToken);

    Task InsertManagedEquationAsync(string ooxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken);

    Task InsertOleFormulaObjectAsync(FormulaMetadata metadata, bool display, CancellationToken cancellationToken);

    Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken);

    Task UpdateFormulaAsync(string equationId, string ooxml, string equationOoxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken);

    Task DeleteSelectedFormulaAsync(CancellationToken cancellationToken);

    Task<int> RenumberAutomaticFormulasAsync(CancellationToken cancellationToken);

    int GetNextAutomaticNumber();

    void SetNextAutomaticNumber(int number);

}
