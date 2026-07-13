using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Editor;

public sealed class FormulaEditorSession : IDisposable
{
    private readonly IFormulaEditor _editor;
    private long _generation;

    public FormulaEditorSession(IFormulaEditor editor)
    {
        _editor = editor ?? throw new ArgumentNullException(nameof(editor));
    }

    public Task WarmUpAsync(CancellationToken cancellationToken)
    {
        return _editor.WarmUpAsync(cancellationToken);
    }

    public bool HasActiveSession { get; private set; }

    public long CurrentGeneration => _generation;

    public FormulaMetadata? CurrentFormula { get; private set; }

    public Task<long> OpenForInsertAsync(FormulaMetadata initialDraft, CancellationToken cancellationToken)
    {
        if (initialDraft == null)
        {
            throw new ArgumentNullException(nameof(initialDraft));
        }

        return OpenAsync(initialDraft, updateMode: false, cancellationToken);
    }

    public Task<long> OpenForEditAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        return OpenAsync(metadata, updateMode: true, cancellationToken);
    }

    public bool IsCurrent(long generation, FormulaIdentity identity)
    {
        if (identity == null)
        {
            throw new ArgumentNullException(nameof(identity));
        }

        return HasActiveSession
            && generation == _generation
            && CurrentFormula != null
            && string.Equals(CurrentFormula.Identity.DocumentId, identity.DocumentId, StringComparison.Ordinal)
            && string.Equals(CurrentFormula.Identity.EquationId, identity.EquationId, StringComparison.Ordinal);
    }

    public bool Complete(long generation)
    {
        if (!HasActiveSession || generation != _generation)
        {
            return false;
        }

        HasActiveSession = false;
        CurrentFormula = null;
        return true;
    }

    private async Task<long> OpenAsync(FormulaMetadata metadata, bool updateMode, CancellationToken cancellationToken)
    {
        long generation = checked(_generation + 1);
        _generation = generation;
        HasActiveSession = true;
        CurrentFormula = metadata;
        try
        {
            await _editor.OpenAsync(metadata, updateMode, generation, cancellationToken).ConfigureAwait(true);
            return generation;
        }
        catch
        {
            if (_generation == generation)
            {
                HasActiveSession = false;
                CurrentFormula = null;
            }

            throw;
        }
    }

    public void Dispose()
    {
        _editor.Dispose();
    }
}
