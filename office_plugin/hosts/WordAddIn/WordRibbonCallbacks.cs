using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordRibbonCallbacks
{
    private readonly WordPluginController _controller;
    private readonly IWordStatusSink _statusSink;
    private readonly Action? _showTaskPane;
    private CancellationTokenSource? _ocrCancellation;
    private int _ocrRunning;

    public WordRibbonCallbacks(WordPluginController controller, IWordStatusSink? statusSink = null, Action? showTaskPane = null)
    {
        _controller = controller ?? throw new ArgumentNullException(nameof(controller));
        _statusSink = statusSink ?? NullWordStatusSink.Instance;
        _showTaskPane = showTaskPane;
        if (SynchronizationContext.Current == null)
        {
            SynchronizationContext.SetSynchronizationContext(new WindowsFormsSynchronizationContext());
        }
    }

    public void OnConnect(object control)
    {
        FireAndForgetSerial(ct => _controller.TestConnectionAsync(ct));
    }

    public void OnInsertOmml(object control)
    {
        FireAndForgetSerial(ct => _controller.InsertOmmlAsync(ct));
    }

    public void OnInsertFromTaskPane(object control)
    {
        FireAndForgetSerial(ct => _controller.InsertFromTaskPaneAsync(ct));
    }

    public void OnInsertInline(object control)
    {
        FireAndForgetSerial(ct => _controller.InsertInlineAsync(ct));
    }

    public void OnInsertDisplay(object control)
    {
        FireAndForgetSerial(ct => _controller.InsertDisplayAsync(ct));
    }

    public void OnInsertNumbered(object control)
    {
        FireAndForgetSerial(ct => _controller.InsertNumberedAsync(ct));
    }

    public void OnLoadSelected(object control)
    {
        FireAndForgetSerial(ct => _controller.LoadSelectedAsync(ct));
    }

    public void OnScreenshotOcr(object control)
    {
        if (Interlocked.CompareExchange(ref _ocrRunning, 1, 0) == 1)
        {
            CancelScreenshotOcr();
            return;
        }

        _ocrCancellation = new CancellationTokenSource();
        _ = RunScreenshotOcrAsync(_ocrCancellation);
    }

    public void OnDeleteSelected(object control)
    {
        FireAndForgetSerial(ct => _controller.DeleteSelectedAsync(ct));
    }

    public void OnAutoNumberSelected(object control)
    {
        FireAndForgetSerial(ct => _controller.AutoNumberSelectedAsync(ct));
    }

    public void OnRenumberAll(object control)
    {
        FireAndForgetSerial(ct => _controller.RenumberAllAsync(ct));
    }

    public void OnShowTaskPane(object control)
    {
        _showTaskPane?.Invoke();
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("TaskPaneShownStatus"));
    }

    public void OnSettings(object control)
    {
        FireAndForgetSerial(ct => _controller.ShowSettingsAsync(ct));
    }

    public void OnHelp(object control)
    {
        FireAndForgetSerial(ct => _controller.ShowHelpAsync(ct));
    }

    private void FireAndForgetSerial(Func<CancellationToken, Task> action)
    {
        FireAndForgetSerial(action, WordAddInText.Get("WorkingStatus"));
    }

    private void FireAndForgetSerial(Func<CancellationToken, Task> action, string startMessage)
    {
        _ = RunSerialAsync(action, startMessage);
    }

    private async Task RunSerialAsync(Func<CancellationToken, Task> action, string startMessage)
    {
        try
        {
            using var timeout = OfficeCommandTimeouts.CreateStandardCommandTokenSource();
            bool ran = await _controller.TryRunCommandAsync(async ct =>
            {
                _statusSink.SetBusy(true);
                _statusSink.Post(WordStatusKind.Info, startMessage);
                await action(ct).ConfigureAwait(true);
            }, timeout.Token).ConfigureAwait(true);
            if (!ran)
            {
                _statusSink.Post(WordStatusKind.Info, startMessage);
            }
        }
        catch (OperationCanceledException)
        {
            _statusSink.Post(WordStatusKind.Error, WordAddInText.Get("CommandTimeoutStatus"));
        }
        catch (Exception exc)
        {
            _statusSink.Post(WordStatusKind.Error, exc.Message);
        }
        finally
        {
            _statusSink.SetBusy(false);
        }
    }

    private async Task RunScreenshotOcrAsync(CancellationTokenSource cancellation)
    {
        try
        {
            _statusSink.SetOcrActive(true);
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OcrWaitingStatus"));
            bool ran = await _controller.TryRunCommandAsync(
                ct => _controller.RecognizeScreenshotAsync(ct),
                cancellation.Token).ConfigureAwait(true);
            if (!ran)
            {
                _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("WorkingStatus"));
            }
        }
        catch (OperationCanceledException)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OcrCanceledStatus"));
        }
        catch (Exception exc)
        {
            _statusSink.Post(WordStatusKind.Error, exc.Message);
        }
        finally
        {
            _statusSink.SetOcrActive(false);
            Interlocked.Exchange(ref _ocrRunning, 0);
            if (ReferenceEquals(_ocrCancellation, cancellation))
            {
                _ocrCancellation = null;
            }

            cancellation.Dispose();
        }
    }

    private void CancelScreenshotOcr()
    {
        try
        {
            _ocrCancellation?.Cancel();
        }
        catch (ObjectDisposedException)
        {
        }

        _ = CancelScreenshotOcrAsync();
    }

    private async Task CancelScreenshotOcrAsync()
    {
        try
        {
            await _controller.CancelScreenshotOcrAsync(CancellationToken.None);
        }
        catch (ObjectDisposedException)
        {
        }
        catch (Exception exc)
        {
            _statusSink.Post(WordStatusKind.Error, exc.Message);
        }
    }
}
