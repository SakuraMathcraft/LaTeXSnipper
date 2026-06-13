using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public interface IWordApplicationAdapter
{
    Task ValidateCurrentInsertionTargetAsync(CancellationToken cancellationToken);

    Task ActivateForEditingAsync(CancellationToken cancellationToken);

    IDisposable BeginUndoRecord();

    double GetCurrentFontSizePoints();

    Task InsertManagedEquationAsync(
        string ooxml,
        FormulaMetadata metadata,
        bool display,
        CancellationToken cancellationToken);

    Task InsertOleFormulaObjectAsync(FormulaMetadata metadata, OlePresentationResult presentation, bool display, CancellationToken cancellationToken);

    Task UpdateOleFormulaObjectAsync(string equationId, FormulaMetadata metadata, OlePresentationResult presentation, bool display, CancellationToken cancellationToken);

    Task ResetOleFormulaObjectAsync(string equationId, FormulaMetadata metadata, OlePresentationResult presentation, bool display, CancellationToken cancellationToken);

    Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken);

    Task<IReadOnlyList<WordFormulaEntry>> LoadSelectedFormulaEntriesAsync(CancellationToken cancellationToken);

    Task UpdateFormulaAsync(string equationId, string ooxml, string equationOoxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken);

    Task ResetManagedEquationFormattingAsync(FormulaMetadata metadata, CancellationToken cancellationToken);

    Task<int> ResetCustomFormulaSizesAsync(CancellationToken cancellationToken);

    bool HasCustomFormulaScale(FormulaMetadata metadata);

    Task<IReadOnlyList<string>> DeleteSelectedFormulaAsync(CancellationToken cancellationToken);

    Task<int> RenumberAutomaticFormulasAsync(CancellationToken cancellationToken);

    int GetNextAutomaticNumber();

    string GetNextAutomaticNumberText();

    void SetNextAutomaticNumber(int number);

    Task InsertReferencePlaceholderAsync(CancellationToken cancellationToken);

    Task<bool> CompletePendingReferenceAsync(CancellationToken cancellationToken);

    Task InsertNumberingBoundaryAsync(WordNumberingBoundary boundary, CancellationToken cancellationToken);

    Task ApplyNumberingBoundaryVisibilityAsync(CancellationToken cancellationToken);

}
