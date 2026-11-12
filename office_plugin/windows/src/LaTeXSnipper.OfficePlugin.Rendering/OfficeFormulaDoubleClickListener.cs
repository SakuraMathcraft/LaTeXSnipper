#if NETFRAMEWORK
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Detects a gesture without doing Office COM work on the mouse hook thread.</summary>
public sealed class OfficeFormulaDoubleClickListener : IDisposable
{
    private readonly OfficeStaDispatcher dispatcher;
    private readonly Action<int, int> editAtPoint;
    private readonly Thread thread;
    private readonly HookCallback callback;
    private readonly TaskCompletionSource<int> ready = new();
    private readonly TextWriterTraceListener? diagnostic;
    private readonly uint processId;
    private uint threadId;
    private IntPtr hook;
    private uint lastTime;
    private Point lastPoint;
    private IntPtr lastWindow;
    private System.Windows.Forms.Timer? pending;
    private volatile bool disposed;

    public OfficeFormulaDoubleClickListener(int officeProcessId, Action<int, int> editAtPoint)
    {
        this.editAtPoint = editAtPoint ?? throw new ArgumentNullException(nameof(editAtPoint));
        if (Thread.CurrentThread.GetApartmentState() != ApartmentState.STA)
            throw new InvalidOperationException("双击监听必须在 Office UI 线程初始化。");
        if (officeProcessId <= 0) throw new ArgumentOutOfRangeException(nameof(officeProcessId));
        processId = (uint)officeProcessId;
        dispatcher = new OfficeStaDispatcher();
        if (!string.IsNullOrEmpty(Environment.GetEnvironmentVariable("LATEXSNIPPER_OLE_LOG")))
        {
            var path = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "LaTeXSnipper", "OfficePlugin", "double-click.log");
            try
            {
                System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path)!);
                diagnostic = new TextWriterTraceListener(path);
            }
            catch (System.IO.IOException error) { Trace.TraceError("Double-click diagnostics: {0}", error); }
            catch (UnauthorizedAccessException error) { Trace.TraceError("Double-click diagnostics: {0}", error); }
        }
        callback = OnMouse;
        thread = new Thread(Listen) { IsBackground = true, Name = "LaTeXSnipper formula double click" };
        thread.Start();
        if (!ready.Task.Wait(TimeSpan.FromSeconds(5)))
        {
            Dispose();
            throw new TimeoutException("公式双击监听启动超时。");
        }
        if (ready.Task.Result != 0)
        {
            Dispose();
            throw new Win32Exception(ready.Task.Result);
        }
        Log("Formula double-click listener initialized, process=" + processId);
    }

    private void Listen()
    {
        threadId = GetCurrentThreadId();
        PeekMessage(out _, IntPtr.Zero, 0, 0, 0);
        hook = SetWindowsHookEx(14, callback, GetModuleHandle(null), 0);
        int error = hook == IntPtr.Zero ? Marshal.GetLastWin32Error() : 0;
        ready.TrySetResult(hook == IntPtr.Zero && error == 0 ? 31 : error);
        if (hook == IntPtr.Zero) return;
        try { while (!disposed && GetMessage(out var message, IntPtr.Zero, 0, 0) > 0) { TranslateMessage(ref message); DispatchMessage(ref message); } }
        finally { UnhookWindowsHookEx(hook); }
    }

    private IntPtr OnMouse(int code, IntPtr message, IntPtr data)
    {
        try
        {
            if (code >= 0 && !disposed && message.ToInt64() == 0x201)
            {
                var mouse = Marshal.PtrToStructure<MouseData>(data);
                var window = GetForegroundWindow();
                GetWindowThreadProcessId(window, out uint owner);
                if (owner == processId)
                {
                    bool doubleClick = lastTime != 0 && window == lastWindow
                        && unchecked(mouse.Time - lastTime) <= GetDoubleClickTime()
                        && Math.Abs(mouse.Position.X - lastPoint.X) <= GetSystemMetrics(36) / 2
                        && Math.Abs(mouse.Position.Y - lastPoint.Y) <= GetSystemMetrics(37) / 2;
                    lastTime = doubleClick ? 0 : mouse.Time;
                    lastPoint = mouse.Position;
                    lastWindow = window;
                    if (doubleClick)
                        _ = dispatcher.InvokeAsync(() => { Schedule(mouse.Position, window); return true; }, CancellationToken.None);
                }
                else lastTime = 0;
            }
        }
        catch (Exception error) { Trace.TraceError("Formula double-click gesture: {0}", error); }
        return CallNextHookEx(hook, code, message, data);
    }

    private void Schedule(Point point, IntPtr window)
    {
        if (disposed) return;
        Log("Formula double-click dispatched at " + point.X + "," + point.Y);
        pending?.Dispose();
        pending = new System.Windows.Forms.Timer { Interval = 60 };
        pending.Tick += (_, _) =>
        {
            pending?.Dispose();
            pending = null;
            if (disposed || GetForegroundWindow() != window) return;
            try { editAtPoint(point.X, point.Y); }
            catch (Exception error) { Trace.TraceError("Formula double-click: {0}", error); }
        };
        pending.Start();
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        pending?.Dispose();
        pending = null;
        PostThreadMessage(threadId, 0x12, UIntPtr.Zero, IntPtr.Zero);
        thread.Join(1000);
        diagnostic?.Dispose();
        dispatcher.Dispose();
    }

    private void Log(string message)
    {
        Trace.WriteLine(message);
        try
        {
            diagnostic?.WriteLine(message);
            diagnostic?.Flush();
        }
        catch (System.IO.IOException error) { Trace.TraceError("Double-click diagnostics: {0}", error); }
        catch (UnauthorizedAccessException error) { Trace.TraceError("Double-click diagnostics: {0}", error); }
    }

    [StructLayout(LayoutKind.Sequential)] private struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] private struct MouseData { public Point Position; public uint MouseDataValue, Flags, Time; public UIntPtr ExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] private struct Message { public IntPtr Window; public uint Id; public UIntPtr WParam; public IntPtr LParam; public uint Time; public Point Position; public uint Private; }
    private delegate IntPtr HookCallback(int code, IntPtr message, IntPtr data);
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr SetWindowsHookEx(int id, HookCallback callback, IntPtr module, uint threadId);
    [DllImport("user32.dll")] private static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")] private static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr message, IntPtr data);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr GetModuleHandle(string? name);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] private static extern int GetMessage(out Message message, IntPtr window, uint first, uint last);
    [DllImport("user32.dll")] private static extern bool PeekMessage(out Message message, IntPtr window, uint first, uint last, uint remove);
    [DllImport("user32.dll")] private static extern bool TranslateMessage(ref Message message);
    [DllImport("user32.dll")] private static extern IntPtr DispatchMessage(ref Message message);
    [DllImport("user32.dll")] private static extern bool PostThreadMessage(uint threadId, uint message, UIntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll")] private static extern uint GetDoubleClickTime();
    [DllImport("user32.dll")] private static extern int GetSystemMetrics(int index);
}
#endif
