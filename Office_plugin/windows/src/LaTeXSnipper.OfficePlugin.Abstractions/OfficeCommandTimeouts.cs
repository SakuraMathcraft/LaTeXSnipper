using System;
using System.Threading;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public static class OfficeCommandTimeouts
{
    public static readonly TimeSpan StandardCommand = TimeSpan.FromSeconds(45);

    public static readonly TimeSpan Render = TimeSpan.FromSeconds(20);

    public static CancellationTokenSource CreateStandardCommandTokenSource()
    {
        return new CancellationTokenSource(StandardCommand);
    }
}
