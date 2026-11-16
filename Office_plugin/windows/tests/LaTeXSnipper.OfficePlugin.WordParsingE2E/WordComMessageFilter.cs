using System;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal sealed class WordComMessageFilter : IDisposable
{
    private const int ServerCallRetryLater = 2;
    private const int RetryDelayMilliseconds = 100;

    private readonly IMessageFilter? _previous;
    private bool _disposed;

    private WordComMessageFilter()
    {
        CoRegisterMessageFilter(new RetryMessageFilter(), out _previous);
    }

    public static WordComMessageFilter Register()
    {
        return new WordComMessageFilter();
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        CoRegisterMessageFilter(_previous, out _);
    }

    [DllImport("ole32.dll")]
    private static extern int CoRegisterMessageFilter(
        IMessageFilter? newFilter,
        out IMessageFilter? oldFilter);

    [ComImport]
    [Guid("00000016-0000-0000-C000-000000000046")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMessageFilter
    {
        [PreserveSig]
        int HandleInComingCall(int callType, IntPtr taskCaller, int tickCount, IntPtr interfaceInfo);

        [PreserveSig]
        int RetryRejectedCall(IntPtr taskCallee, int tickCount, int rejectType);

        [PreserveSig]
        int MessagePending(IntPtr taskCallee, int tickCount, int pendingType);
    }

    private sealed class RetryMessageFilter : IMessageFilter
    {
        public int HandleInComingCall(int callType, IntPtr taskCaller, int tickCount, IntPtr interfaceInfo)
        {
            return 0;
        }

        public int RetryRejectedCall(IntPtr taskCallee, int tickCount, int rejectType)
        {
            return rejectType == ServerCallRetryLater ? RetryDelayMilliseconds : -1;
        }

        public int MessagePending(IntPtr taskCallee, int tickCount, int pendingType)
        {
            return 2;
        }
    }
}
