using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class MathLiveFormulaEditor : IFormulaEditor
{
    private MathLiveFormulaEditorForm? _activeForm;

    public event EventHandler<FormulaEditorAcceptedEventArgs>? FormulaAccepted;

    public event EventHandler<string>? EditorError;

    public Task<FormulaMetadata?> OpenAsync(FormulaMetadata? initialFormula, bool updateMode, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        MathLiveFormulaEditorForm form = GetOrCreateForm();
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

        _activeForm = new MathLiveFormulaEditorForm();
        _activeForm.FormulaAccepted += OnFormulaAccepted;
        _activeForm.EditorError += OnEditorError;
        _activeForm.FormClosed += OnFormClosed;
        return _activeForm;
    }

    private void OnFormulaAccepted(object? sender, FormulaEditorAcceptedEventArgs e)
    {
        FormulaAccepted?.Invoke(this, e);
    }

    private void OnFormClosed(object? sender, FormClosedEventArgs e)
    {
        if (_activeForm == null)
        {
            return;
        }

        _activeForm.FormulaAccepted -= OnFormulaAccepted;
        _activeForm.EditorError -= OnEditorError;
        _activeForm.FormClosed -= OnFormClosed;
        _activeForm = null;
    }

    private void OnEditorError(object? sender, string message)
    {
        EditorError?.Invoke(this, message);
    }
}
