using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Editor;

public sealed class FormulaEditorSession : IDisposable
{
    private readonly IFormulaEditor _editor;

    public FormulaEditorSession(IFormulaEditor editor)
    {
        _editor = editor ?? throw new ArgumentNullException(nameof(editor));
    }

    public Task WarmUpAsync(CancellationToken cancellationToken)
    {
        return _editor.WarmUpAsync(cancellationToken);
    }

    public Task<FormulaMetadata?> OpenForInsertAsync(CancellationToken cancellationToken)
    {
        return _editor.OpenAsync(null, updateMode: false, cancellationToken);
    }

    public Task<FormulaMetadata?> OpenForInsertAsync(FormulaMetadata initialDraft, CancellationToken cancellationToken)
    {
        if (initialDraft == null)
        {
            throw new ArgumentNullException(nameof(initialDraft));
        }

        return _editor.OpenAsync(initialDraft, updateMode: false, cancellationToken);
    }

    public Task<FormulaMetadata?> OpenForEditAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        return _editor.OpenAsync(metadata, updateMode: true, cancellationToken);
    }

    public Task<bool> UpdateDraftIfOpenAsync(FormulaMetadata draft, bool updateMode, CancellationToken cancellationToken)
    {
        if (draft == null)
        {
            throw new ArgumentNullException(nameof(draft));
        }

        return _editor.UpdateDraftIfOpenAsync(draft, updateMode, cancellationToken);
    }

    public void Dispose()
    {
        _editor.Dispose();
    }
}
