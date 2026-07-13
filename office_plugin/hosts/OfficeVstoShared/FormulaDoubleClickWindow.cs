using System;
using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.VstoShared
{
    internal sealed class FormulaDoubleClickWindow : NativeWindow, IDisposable
    {
        private const int WmLeftButtonDoubleClick = 0x0203;
        private const int WmImageActivation = 0x84C1;
        private const int WhMouse = 7;
        private const int DuplicateWindowMilliseconds = 500;
        private readonly Action activationRequested;
        private readonly int oleActivationMessage;
        private readonly NativeMethods.HookProcedure mouseHookProcedure;
        private IntPtr mouseHook;
        private int lastActivationTick;

        public FormulaDoubleClickWindow(IntPtr windowHandle, Action activationRequested)
        {
            this.activationRequested = activationRequested ?? throw new ArgumentNullException(nameof(activationRequested));
            oleActivationMessage = NativeMethods.RegisterWindowMessage("LaTeXSnipper.OfficePlugin.OleFormulaActivate");
            if (oleActivationMessage == 0)
            {
                throw new InvalidOperationException("Cannot register the OLE formula activation message.");
            }

            lastActivationTick = unchecked(Environment.TickCount - DuplicateWindowMilliseconds);
            AssignHandle(windowHandle);
            mouseHookProcedure = OnMouseMessage;
            mouseHook = NativeMethods.SetWindowsHookEx(WhMouse, mouseHookProcedure, IntPtr.Zero, NativeMethods.GetCurrentThreadId());
            if (mouseHook == IntPtr.Zero)
            {
                ReleaseHandle();
                throw new InvalidOperationException("Cannot install the Office formula double-click hook.");
            }
        }

        protected override void WndProc(ref Message message)
        {
            bool isActivation = message.Msg == WmImageActivation || message.Msg == oleActivationMessage;
            base.WndProc(ref message);
            if (!isActivation)
            {
                return;
            }

            int now = Environment.TickCount;
            if (unchecked((uint)(now - lastActivationTick)) < DuplicateWindowMilliseconds)
            {
                return;
            }

            lastActivationTick = now;
            activationRequested();
        }

        public void Dispose()
        {
            if (mouseHook != IntPtr.Zero)
            {
                NativeMethods.UnhookWindowsHookEx(mouseHook);
                mouseHook = IntPtr.Zero;
            }

            ReleaseHandle();
        }

        private IntPtr OnMouseMessage(int code, IntPtr message, IntPtr data)
        {
            if (code >= 0 && message.ToInt32() == WmLeftButtonDoubleClick)
            {
                NativeMethods.PostMessage(Handle, WmImageActivation, IntPtr.Zero, IntPtr.Zero);
            }

            return NativeMethods.CallNextHookEx(mouseHook, code, message, data);
        }

        private static class NativeMethods
        {
            internal delegate IntPtr HookProcedure(int code, IntPtr message, IntPtr data);

            [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
            internal static extern int RegisterWindowMessage(string message);

            [System.Runtime.InteropServices.DllImport("user32.dll")]
            internal static extern IntPtr SetWindowsHookEx(int hookType, HookProcedure procedure, IntPtr module, uint threadId);

            [System.Runtime.InteropServices.DllImport("user32.dll")]
            [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
            internal static extern bool UnhookWindowsHookEx(IntPtr hook);

            [System.Runtime.InteropServices.DllImport("user32.dll")]
            internal static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr message, IntPtr data);

            [System.Runtime.InteropServices.DllImport("user32.dll")]
            [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
            internal static extern bool PostMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);

            [System.Runtime.InteropServices.DllImport("kernel32.dll")]
            internal static extern uint GetCurrentThreadId();
        }
    }
}
