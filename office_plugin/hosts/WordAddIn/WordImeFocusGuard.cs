using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal sealed class WordImeFocusGuard : IDisposable
{
    private readonly List<PaneWindow> _panes = new();

    public WordImeFocusGuard(IntPtr wordWindow)
    {
        if (wordWindow == IntPtr.Zero)
            return;

        try
        {
            EnumChildWindows(wordWindow, (window, _) =>
            {
                var className = new StringBuilder(32);
                GetClassName(window, className, className.Capacity);
                if (className.ToString() == "_WwG")
                {
                    var pane = new PaneWindow();
                    pane.AssignHandle(window);
                    _panes.Add(pane);
                }

                return true;
            }, IntPtr.Zero);
        }
        catch
        {
            Dispose();
            throw;
        }
    }

    public void Dispose()
    {
        foreach (PaneWindow pane in _panes)
            pane.ReleaseHandle();
        _panes.Clear();
    }

    private sealed class PaneWindow : NativeWindow
    {
        protected override void WndProc(ref Message message)
        {
            // Word can receive a stale RECONVERTSTRING while SetFocus dispatches IME requests (#411).
            if (message.Msg == 0x0288 && message.WParam == new IntPtr(7))
            {
                message.Result = IntPtr.Zero;
                return;
            }

            base.WndProc(ref message);
        }
    }

    private delegate bool EnumWindowCallback(IntPtr window, IntPtr parameter);

    [DllImport("user32.dll")]
    private static extern bool EnumChildWindows(IntPtr parent, EnumWindowCallback callback, IntPtr parameter);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr window, StringBuilder className, int maxCount);
}
