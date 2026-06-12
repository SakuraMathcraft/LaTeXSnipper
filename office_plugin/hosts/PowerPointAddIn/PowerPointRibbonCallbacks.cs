using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointRibbonCallbacks
{
    private readonly PowerPointPluginController _controller;
    private readonly IPowerPointStatusSink _statusSink;
    private readonly Action? _showTaskPane;
    private CancellationTokenSource? _ocrCancellation;
    private int _ocrRunning;

    public PowerPointRibbonCallbacks(PowerPointPluginController controller, IPowerPointStatusSink? statusSink = null, Action? showTaskPane = null)
    {
        _controller = controller ?? throw new ArgumentNullException(nameof(controller));
        _statusSink = statusSink ?? NullPowerPointStatusSink.Instance;
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

    public void OnInsertFormula(object control)
    {
        FireAndForgetSerial(ct => _controller.InsertFormulaAsync(ct));
    }

    public void OnInsertFromTaskPane(object control)
    {
        FireAndForgetSerial(ct => _controller.InsertFormulaFromTaskPaneAsync(ct));
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

    public void OnConvertSelectedToOle(object control) => FireAndForgetSerial(ct => _controller.ConvertSelectedToOleAsync(ct));

    public void OnConvertSelectedToPng(object control) => FireAndForgetSerial(ct => _controller.ConvertSelectedToPngAsync(ct));

    public void OnFormatSelected(object control) => FireAndForgetSerial(ct => _controller.FormatSelectedAsync(ct));

    public void OnFormatAll(object control) => FireAndForgetSerial(ct => _controller.FormatAllAsync(ct));

    public void OnShowTaskPane(object control)
    {
        _showTaskPane?.Invoke();
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("TaskPaneShownStatus"));
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
        _ = RunSerialAsync(action);
    }

    private async Task RunSerialAsync(Func<CancellationToken, Task> action)
    {
        try
        {
            using var timeout = OfficeCommandTimeouts.CreateStandardCommandTokenSource();
            bool ran = await _controller.TryRunCommandAsync(async ct =>
            {
                _statusSink.SetBusy(true);
                _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("WorkingStatus"));
                await action(ct).ConfigureAwait(true);
            }, timeout.Token).ConfigureAwait(true);
            if (!ran)
            {
                _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("WorkingStatus"));
            }
        }
        catch (OperationCanceledException)
        {
            _statusSink.Post(PowerPointStatusKind.Error, PowerPointAddInText.Get("CommandTimeoutStatus"));
        }
        catch (Exception exc)
        {
            _statusSink.Post(PowerPointStatusKind.Error, exc.Message);
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
            _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("OcrWaitingStatus"));
            await _controller.RecognizeScreenshotAsync(cancellation.Token).ConfigureAwait(true);
        }
        catch (OperationCanceledException)
        {
            _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("OcrCanceledStatus"));
        }
        catch (Exception exc)
        {
            _statusSink.Post(PowerPointStatusKind.Error, exc.Message);
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
            _statusSink.Post(PowerPointStatusKind.Error, exc.Message);
        }
    }
}
