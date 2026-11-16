#if NETFRAMEWORK
using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Marshals Office work to the STA thread that created the adapter.</summary>
public sealed class OfficeStaDispatcher : IDisposable
{
    private readonly int threadId = Thread.CurrentThread.ManagedThreadId;
    private readonly Control control;
    private bool disposed;

    public OfficeStaDispatcher()
    {
        if (Thread.CurrentThread.GetApartmentState() != ApartmentState.STA)
            throw new InvalidOperationException("Office 调度器必须在主 STA 线程初始化。");
        // Own a marshaling handle; Office's base SynchronizationContext can use the thread pool.
        control = new Control();
        _ = control.Handle;
    }

    public Task<T> InvokeAsync<T>(Func<T> action, CancellationToken cancellationToken)
    {
        if (disposed) throw new ObjectDisposedException(nameof(OfficeStaDispatcher));
        cancellationToken.ThrowIfCancellationRequested();
        if (Thread.CurrentThread.ManagedThreadId == threadId) return Task.FromResult(action());
        var completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        control.BeginInvoke(new Action(() =>
        {
            try
            {
                if (disposed) throw new ObjectDisposedException(nameof(OfficeStaDispatcher));
                cancellationToken.ThrowIfCancellationRequested();
                completion.TrySetResult(action());
            }
            catch (OperationCanceledException) { completion.TrySetCanceled(); }
            catch (Exception error) { completion.TrySetException(error); }
        }));
        return completion.Task;
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        if (Thread.CurrentThread.ManagedThreadId == threadId) control.Dispose();
        else control.BeginInvoke(new Action(control.Dispose));
    }
}
#endif
