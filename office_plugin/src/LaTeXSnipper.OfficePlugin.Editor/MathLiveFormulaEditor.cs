#if NET48
using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Editor;

public sealed class MathLiveFormulaEditor : IFormulaEditor
{
    private readonly MathLiveFormulaEditorOptions _options;
    private MathLiveFormulaEditorForm? _activeForm;
    private bool _disposed;

    public MathLiveFormulaEditor(MathLiveFormulaEditorOptions options)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
    }

    public event Func<FormulaEditorAcceptedEventArgs, Task<FormulaEditorSubmissionResult>>? FormulaSubmitting;

    public event EventHandler? EditorCancelled;

    public event EventHandler<string>? EditorError;

    public Task WarmUpAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();
        return GetOrCreateForm().WarmUpAsync();
    }

    public Task<FormulaMetadata?> OpenAsync(FormulaMetadata? initialFormula, bool updateMode, CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();
        MathLiveFormulaEditorForm form = GetOrCreateForm();
        form.CloseOnCommit = false;
        form.Configure(initialFormula, updateMode);
        form.Show();
        if (form.WindowState == FormWindowState.Minimized)
        {
            form.WindowState = FormWindowState.Normal;
        }

        form.Activate();
        return Task.FromResult<FormulaMetadata?>(null);
    }

    public Task<bool> UpdateDraftIfOpenAsync(FormulaMetadata draft, bool updateMode, CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();
        if (_activeForm == null || _activeForm.IsDisposed || !_activeForm.Visible)
        {
            return Task.FromResult(false);
        }

        _activeForm.Configure(draft, updateMode);
        return Task.FromResult(true);
    }

    private MathLiveFormulaEditorForm GetOrCreateForm()
    {
        if (_activeForm != null && !_activeForm.IsDisposed)
        {
            return _activeForm;
        }

        _activeForm = new MathLiveFormulaEditorForm(_options);
        _activeForm.FormulaSubmitting += OnFormulaSubmittingAsync;
        _activeForm.EditorCancelled += OnEditorCancelled;
        _activeForm.EditorError += OnEditorError;
        _activeForm.FormClosed += OnFormClosed;
        return _activeForm;
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        if (_activeForm != null && !_activeForm.IsDisposed)
        {
            _activeForm.DisposeForShutdown();
        }
    }

    private Task<FormulaEditorSubmissionResult> OnFormulaSubmittingAsync(FormulaEditorAcceptedEventArgs e)
    {
        Func<FormulaEditorAcceptedEventArgs, Task<FormulaEditorSubmissionResult>>? handler = FormulaSubmitting;
        return handler == null
            ? Task.FromResult(FormulaEditorSubmissionResult.Rejected("Formula submit handler is not connected."))
            : handler(e);
    }

    private void OnFormClosed(object? sender, FormClosedEventArgs e)
    {
        if (_activeForm == null)
        {
            return;
        }

        _activeForm.FormulaSubmitting -= OnFormulaSubmittingAsync;
        _activeForm.EditorCancelled -= OnEditorCancelled;
        _activeForm.EditorError -= OnEditorError;
        _activeForm.FormClosed -= OnFormClosed;
        _activeForm = null;
    }

    private void OnEditorCancelled(object? sender, EventArgs e)
    {
        EditorCancelled?.Invoke(this, EventArgs.Empty);
    }

    private void OnEditorError(object? sender, string message)
    {
        EditorError?.Invoke(this, message);
    }

    private void ThrowIfDisposed()
    {
        if (_disposed)
        {
            throw new ObjectDisposedException(nameof(MathLiveFormulaEditor));
        }
    }
}
#endif
