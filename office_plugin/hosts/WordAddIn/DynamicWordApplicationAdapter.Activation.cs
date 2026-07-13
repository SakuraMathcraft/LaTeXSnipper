using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    public Task ActivateForEditingAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        TryCom(() => _wordApplication.Activate());
        TryCom(() => _wordApplication.ActiveWindow.Activate());
        TryCom(() => _wordApplication.ActiveWindow.SetFocus());
        TryCom(() => SetForegroundWindow(new IntPtr(Convert.ToInt32(_wordApplication.ActiveWindow.Hwnd))));
        TryCom(() => SetForegroundWindow(new IntPtr(Convert.ToInt32(_wordApplication.Hwnd))));
        ResetSelectionFormulaTextFormatting();
        return Task.CompletedTask;
    }

    public Task ActivateFormulaEditTargetAsync(
        WordFormulaEditTarget target,
        CancellationToken cancellationToken)
    {
        if (target == null)
        {
            throw new ArgumentNullException(nameof(target));
        }

        cancellationToken.ThrowIfCancellationRequested();
        dynamic window = target.Window;
        TryCom(() => _wordApplication.Activate());
        TryCom(() => window.Activate());
        TryCom(() => window.SetFocus());
        TryCom(() => SetForegroundWindow(new IntPtr(target.WindowHandle)));
        TryCom(() => SetForegroundWindow(new IntPtr(Convert.ToInt32(_wordApplication.Hwnd))));
        using (UseDocument(target.Document))
        {
            ResetSelectionFormulaTextFormatting();
        }

        return Task.CompletedTask;
    }
}
