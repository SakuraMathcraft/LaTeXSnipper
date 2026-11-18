using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

/// <summary>Handles native double-clicks before PowerPoint can activate the OLE server.</summary>
internal sealed class PowerPointMathTypeDoubleClickHook : IDisposable
{
    private const int WhGetMessage = 3;
    private const int PmRemove = 1;
    private const int WmNull = 0;
    private const int WmLeftButtonDoubleClick = 0x0203;
    private readonly Func<IntPtr, int, int, bool> _tryOpen;
    private readonly GetMessageProc _callback;
    private IntPtr _hook;

    public PowerPointMathTypeDoubleClickHook(Func<IntPtr, int, int, bool> tryOpen)
    {
        _tryOpen = tryOpen;
        _callback = HandleMessage;
        _hook = SetWindowsHookEx(WhGetMessage, _callback, IntPtr.Zero, GetCurrentThreadId());
        if (_hook == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
    }

    private IntPtr HandleMessage(int code, IntPtr removed, IntPtr data)
    {
        if (code == 0 && removed.ToInt64() == PmRemove && Marshal.ReadInt32(data, IntPtr.Size) == WmLeftButtonDoubleClick)
        {
            try
            {
                var message = Marshal.PtrToStructure<WindowMessage>(data);
                long coordinates = message.LParam.ToInt64();
                var point = new Point { X = (short)coordinates, Y = (short)(coordinates >> 16) };
                if (ClientToScreen(message.Window, ref point) && _tryOpen(message.Window, point.X, point.Y))
                    Marshal.WriteInt32(data, IntPtr.Size, WmNull);
            }
            catch (Exception error) { Trace.TraceError("PowerPoint MathType double-click: {0}", error); }
        }
        return CallNextHookEx(_hook, code, removed, data);
    }

    public void Dispose()
    {
        if (_hook == IntPtr.Zero) return;
        UnhookWindowsHookEx(_hook);
        _hook = IntPtr.Zero;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WindowMessage
    {
        public IntPtr Window;
        public uint Id;
        public IntPtr WParam;
        public IntPtr LParam;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Point { public int X, Y; }

    private delegate IntPtr GetMessageProc(int code, IntPtr removed, IntPtr data);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int id, GetMessageProc callback, IntPtr module, uint thread);
    [DllImport("user32.dll")]
    private static extern bool ClientToScreen(IntPtr window, ref Point point);
    [DllImport("user32.dll")]
    private static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr message, IntPtr data);
    [DllImport("user32.dll")]
    private static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();
}
