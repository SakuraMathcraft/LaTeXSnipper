using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointFormulaEditor : IFormulaEditor
{
    private PowerPointFormulaEditorForm? _activeForm;

    public event EventHandler<FormulaEditorAcceptedEventArgs>? FormulaAccepted;

    public event EventHandler? EditorCancelled;

    public event EventHandler<string>? EditorError;

    public Task<FormulaMetadata?> OpenAsync(FormulaMetadata? initialFormula, bool updateMode, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        PowerPointFormulaEditorForm form = GetOrCreateForm();
        form.Configure(initialFormula, updateMode);
        form.Show();
        if (form.WindowState == System.Windows.Forms.FormWindowState.Minimized)
        {
            form.WindowState = System.Windows.Forms.FormWindowState.Normal;
        }

        form.Activate();
        return Task.FromResult<FormulaMetadata?>(null);
    }

    public Task<bool> UpdateDraftIfOpenAsync(FormulaMetadata draft, bool updateMode, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (_activeForm == null || _activeForm.IsDisposed || !_activeForm.Visible)
        {
            return Task.FromResult(false);
        }

        _activeForm.Configure(draft, updateMode);
        return Task.FromResult(true);
    }

    private PowerPointFormulaEditorForm GetOrCreateForm()
    {
        if (_activeForm != null && !_activeForm.IsDisposed)
        {
            return _activeForm;
        }

        _activeForm = new PowerPointFormulaEditorForm();
        _activeForm.FormulaAccepted += OnFormulaAccepted;
        _activeForm.EditorCancelled += OnEditorCancelled;
        _activeForm.EditorError += OnEditorError;
        _activeForm.FormClosed += OnFormClosed;
        return _activeForm;
    }

    private void OnFormulaAccepted(object? sender, FormulaEditorAcceptedEventArgs e)
    {
        FormulaAccepted?.Invoke(this, e);
    }

    private void OnFormClosed(object? sender, System.Windows.Forms.FormClosedEventArgs e)
    {
        EditorCancelled?.Invoke(this, EventArgs.Empty);

        if (_activeForm == null)
        {
            return;
        }

        _activeForm.FormulaAccepted -= OnFormulaAccepted;
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
}
