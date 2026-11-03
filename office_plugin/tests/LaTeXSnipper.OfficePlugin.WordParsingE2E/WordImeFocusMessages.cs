using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class WordImeFocusMessages
{
    public static void Verify()
    {
        using var parent = new Control();
        WindowProcedure procedure = (window, message, wParam, lParam) =>
            message == 0x0288 || message == 0x8051
                ? new IntPtr(123)
                : DefWindowProc(window, message, wParam, lParam);
        var windowClass = new WindowClass
        {
            Instance = GetModuleHandle(null),
            ClassName = "_WwG",
            Procedure = Marshal.GetFunctionPointerForDelegate(procedure),
        };
        if (RegisterClass(ref windowClass) == 0)
            throw new Win32Exception(Marshal.GetLastWin32Error());

        IntPtr pane = IntPtr.Zero;
        try
        {
            pane = CreateWindowEx(0, "_WwG", "", 0x40000000, 0, 0, 1, 1,
                parent.Handle, IntPtr.Zero, windowClass.Instance, IntPtr.Zero);
            if (pane == IntPtr.Zero)
                throw new Win32Exception(Marshal.GetLastWin32Error());

            var application = new ImeMessageWordApplication(parent.Handle, pane);
            using var adapter = new DynamicWordApplicationAdapter(application);
            adapter.ActivateForEditingAsync(CancellationToken.None).GetAwaiter().GetResult();
            if (application.Activations != 3)
                throw new InvalidOperationException("The focus transaction did not complete.");
            Expect(pane, 0x0288, 7, IntPtr.Zero, 123);
            Expect(pane, 0x0288, 7, new IntPtr(-1), 123);
            using var cancelled = new CancellationTokenSource();
            cancelled.Cancel();
            try
            {
                adapter.ActivateForEditingAsync(cancelled.Token).GetAwaiter().GetResult();
                throw new InvalidOperationException("Cancelled activation completed.");
            }
            catch (OperationCanceledException) { }
            if (application.Activations != 3)
                throw new InvalidOperationException("Cancelled activation touched Word.");
            Console.WriteLine("PASS|IMR_DOCUMENTFEED is rejected during focus; other requests pass; normal handling resumes afterward");
        }
        finally
        {
            if (pane != IntPtr.Zero) DestroyWindow(pane);
            UnregisterClass("_WwG", windowClass.Instance);
            GC.KeepAlive(procedure);
        }
    }

    internal static void Expect(IntPtr pane, int message, int request, IntPtr buffer, long expected)
    {
        if (SendMessage(pane, message, new IntPtr(request), buffer).ToInt64() != expected)
            throw new InvalidOperationException("Unexpected IME message result.");
    }

    private delegate IntPtr WindowProcedure(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WindowClass
    {
        public uint Style;
        public IntPtr Procedure;
        public int ClassExtra, WindowExtra;
        public IntPtr Instance, Icon, Cursor, Background;
        public string? MenuName;
        public string ClassName;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandle(string? name);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern ushort RegisterClass(ref WindowClass windowClass);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool UnregisterClass(string name, IntPtr instance);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateWindowEx(int extendedStyle, string className, string title,
        int style, int x, int y, int width, int height, IntPtr parent, IntPtr menu, IntPtr instance, IntPtr parameter);
    [DllImport("user32.dll")]
    private static extern bool DestroyWindow(IntPtr window);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr DefWindowProc(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);
}

public sealed class ImeMessageWordApplication
{
    private readonly IntPtr _pane;
    public ImeMessageWordApplication(IntPtr parent, IntPtr pane) { Hwnd = parent.ToInt32(); _pane = pane; }
    public ImeMessageWordApplication ActiveWindow => this;
    public int Hwnd { get; }
    public int Activations { get; private set; }
    public void SetFocus() => Activate();
    public void Activate()
    {
        WordImeFocusMessages.Expect(_pane, 0x0288, 7, IntPtr.Zero, 0);
        WordImeFocusMessages.Expect(_pane, 0x0288, 7, new IntPtr(-1), 0);
        WordImeFocusMessages.Expect(_pane, 0x0288, 6, IntPtr.Zero, 123);
        WordImeFocusMessages.Expect(_pane, 0x8051, 7, IntPtr.Zero, 123);
        Activations++;
    }
}
