using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

internal static class PowerPointGesture
{
    public static void PostDoubleClick(int processId, int x, int y)
    {
        IntPtr originalContext = SetThreadDpiAwarenessContext(new IntPtr(-4));
        if (originalContext == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        try { PostDoubleClickAtScreenPoint(processId, x, y); }
        finally { SetThreadDpiAwarenessContext(originalContext); }
    }

    private static void PostDoubleClickAtScreenPoint(int processId, int x, int y)
    {
        IntPtr window = IntPtr.Zero;
        EnumWindows((candidate, _) =>
        {
            GetWindowThreadProcessId(candidate, out uint owner);
            if (owner != processId || !IsWindowVisible(candidate) || WindowClass(candidate) != "PPTFrameClass") return true;
            if (!GetWindowRect(candidate, out var bounds) || x < bounds.Left || x >= bounds.Right || y < bounds.Top || y >= bounds.Bottom) return true;
            window = candidate;
            return false;
        }, IntPtr.Zero);
        if (window == IntPtr.Zero) throw new InvalidOperationException($"PowerPoint has no presentation window at ({x}, {y})");
        var screenPoint = new Point { X = x, Y = y };
        Point clientPoint;
        while (true)
        {
            clientPoint = screenPoint;
            if (!ScreenToClient(window, ref clientPoint)) throw new Win32Exception(Marshal.GetLastWin32Error());
            IntPtr child = ChildWindowFromPointEx(window, clientPoint, 7);
            if (child == IntPtr.Zero || child == window) break;
            window = child;
        }
        int position = (clientPoint.Y << 16) | (clientPoint.X & 0xffff);
        if (!PostMessage(window, 0x0203, new IntPtr(1), new IntPtr(position)))
            throw new Win32Exception(Marshal.GetLastWin32Error());
    }

    public static bool HasEditorWindow(int processId)
    {
        bool found = false;
        EnumWindows((window, _) =>
        {
            GetWindowThreadProcessId(window, out uint owner);
            if (owner != processId || !IsWindowVisible(window)) return true;
            var title = new StringBuilder(120);
            GetWindowText(window, title, title.Capacity);
            found = title.ToString() == "LaTeXSnipper" && WindowClass(window).StartsWith("WindowsForms10.", StringComparison.Ordinal);
            return !found;
        }, IntPtr.Zero);
        return found;
    }

    private static string WindowClass(IntPtr window)
    {
        var name = new StringBuilder(120);
        GetClassName(window, name, name.Capacity);
        return name.ToString();
    }

    [StructLayout(LayoutKind.Sequential)] private struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] private struct Rectangle { public int Left, Top, Right, Bottom; }
    private delegate bool WindowVisitor(IntPtr window, IntPtr data);
    [DllImport("user32.dll")] private static extern bool EnumWindows(WindowVisitor visitor, IntPtr data);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr window, out Rectangle rectangle);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr window, StringBuilder text, int capacity);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr window, StringBuilder text, int capacity);
    [DllImport("user32.dll", SetLastError = true)] private static extern bool ScreenToClient(IntPtr window, ref Point point);
    [DllImport("user32.dll")] private static extern IntPtr ChildWindowFromPointEx(IntPtr parent, Point point, uint flags);
    [DllImport("user32.dll", SetLastError = true)] private static extern bool PostMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
}
