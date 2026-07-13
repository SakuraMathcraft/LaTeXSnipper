using System;
using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.VstoShared
{
    internal sealed class OleActivationMessageWindow : NativeWindow, IDisposable
    {
        private readonly Action activationRequested;
        private readonly int activationMessage;
        private bool disposed;

        public OleActivationMessageWindow(IntPtr windowHandle, Action activationRequested)
        {
            if (windowHandle == IntPtr.Zero)
            {
                throw new ArgumentException("An Office window handle is required.", nameof(windowHandle));
            }

            this.activationRequested = activationRequested ?? throw new ArgumentNullException(nameof(activationRequested));
            activationMessage = NativeMethods.RegisterWindowMessage("LaTeXSnipper.OfficePlugin.OleFormulaActivate");
            if (activationMessage == 0)
            {
                throw new InvalidOperationException("Cannot register the OLE formula activation message.");
            }

            AssignHandle(windowHandle);
        }

        public void ReassignHandle(IntPtr windowHandle)
        {
            if (disposed)
            {
                throw new ObjectDisposedException(nameof(OleActivationMessageWindow));
            }

            if (windowHandle == IntPtr.Zero || windowHandle == Handle)
            {
                return;
            }

            ReleaseHandle();
            AssignHandle(windowHandle);
        }

        protected override void WndProc(ref Message message)
        {
            bool isActivation = message.Msg == activationMessage;
            base.WndProc(ref message);
            if (isActivation)
            {
                activationRequested();
            }
        }

        public void Dispose()
        {
            if (disposed)
            {
                return;
            }

            disposed = true;
            ReleaseHandle();
        }

        private static class NativeMethods
        {
            [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
            internal static extern int RegisterWindowMessage(string message);
        }
    }
}
