using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointPluginController : IDisposable
{
    internal const string DefaultLatex = "e^{i\\pi}+1=0";

    private readonly FormulaEditorSession _editorSession;
    private readonly BridgeClient _bridgeClient;
    private readonly IPowerPointApplicationAdapter _powerPointAdapter;
    private readonly IPowerPointStatusSink _statusSink;
    private readonly IPowerPointFormulaOptionsProvider _optionsProvider;
    private readonly PowerPointImageFileStore _imageFileStore;
    private readonly IFormulaRenderer _oleIntermediateRenderer;
    private readonly OlePresentationPipeline _olePresentationPipeline;
    private readonly SemaphoreSlim _commandGate = new SemaphoreSlim(1, 1);
    private float _loadedShapeLeft;
    private float _loadedShapeTop;
    private float _loadedShapeScale;
    private bool _hasLoadedShapePosition;
    private bool _disposed;

    public PowerPointPluginController(
        FormulaEditorSession editorSession,
        BridgeClient bridgeClient,
        IPowerPointApplicationAdapter powerPointAdapter,
        IFormulaRenderer oleIntermediateRenderer,
        OlePresentationPipeline olePresentationPipeline,
        IPowerPointStatusSink? statusSink = null,
        IPowerPointFormulaOptionsProvider? optionsProvider = null,
        PowerPointImageFileStore? imageFileStore = null)
    {
        _editorSession = editorSession ?? throw new ArgumentNullException(nameof(editorSession));
        _bridgeClient = bridgeClient ?? throw new ArgumentNullException(nameof(bridgeClient));
        _powerPointAdapter = powerPointAdapter ?? throw new ArgumentNullException(nameof(powerPointAdapter));
        _oleIntermediateRenderer = oleIntermediateRenderer ?? throw new ArgumentNullException(nameof(oleIntermediateRenderer));
        _olePresentationPipeline = olePresentationPipeline ?? throw new ArgumentNullException(nameof(olePresentationPipeline));
        _statusSink = statusSink ?? NullPowerPointStatusSink.Instance;
        _optionsProvider = optionsProvider ?? DefaultPowerPointFormulaOptionsProvider.Instance;
        _imageFileStore = imageFileStore ?? new PowerPointImageFileStore();
    }

    public async Task TestConnectionAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        await _bridgeClient.ConfigureAsync(cancellationToken);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("ConnectedBridgeStatus"));
    }

    public async Task<bool> TryRunCommandAsync(Func<CancellationToken, Task> command, CancellationToken cancellationToken)
    {
        if (command == null)
        {
            throw new ArgumentNullException(nameof(command));
        }

        ThrowIfDisposed();
        cancellationToken.ThrowIfCancellationRequested();
        if (!await _commandGate.WaitAsync(0, cancellationToken).ConfigureAwait(true))
        {
            return false;
        }

        try
        {
            await command(cancellationToken).ConfigureAwait(true);
            return true;
        }
        finally
        {
            _commandGate.Release();
        }
    }

    public async Task<FormulaEditorSubmissionResult> TryAcceptEditorFormulaAsync(FormulaEditorAcceptedEventArgs accepted, CancellationToken cancellationToken)
    {
        try
        {
            bool acceptedCommand = await TryRunCommandAsync(
                ct => AcceptEditorFormulaAsync(accepted, ct),
                cancellationToken).ConfigureAwait(true);
            if (!acceptedCommand)
            {
                string busyMessage = PowerPointAddInText.Get("WorkingStatus");
                _statusSink.Post(PowerPointStatusKind.Info, busyMessage);
                return FormulaEditorSubmissionResult.Rejected(busyMessage);
            }

            return FormulaEditorSubmissionResult.Accepted();
        }
        catch (OperationCanceledException)
        {
            string message = PowerPointAddInText.Get("CommandTimeoutStatus");
            _statusSink.Post(PowerPointStatusKind.Error, message);
            return FormulaEditorSubmissionResult.Rejected(message);
        }
        catch (Exception exc)
        {
            _statusSink.Post(PowerPointStatusKind.Error, exc.Message);
            return FormulaEditorSubmissionResult.Rejected(exc.Message);
        }
    }

    public async Task WarmUpAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        await _editorSession.WarmUpAsync(cancellationToken);
        if (_oleIntermediateRenderer is MathJaxSvgRenderer mathJaxRenderer)
        {
            await mathJaxRenderer.WarmUpAsync(cancellationToken);
        }
    }

    public async Task InsertFormulaAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        _hasLoadedShapePosition = false;
        FormulaMetadata draft = CreateEditorDraft();
        await _editorSession.OpenForInsertAsync(draft, cancellationToken);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("EditorReadyStatus"));
    }

    public async Task InsertFormulaFromTaskPaneAsync(CancellationToken cancellationToken)
    {
        string latex = _optionsProvider.CurrentLatex;
        if (string.IsNullOrWhiteSpace(latex))
        {
            latex = DefaultLatex;
        }

        FormulaMetadata metadata = CreateMetadata(latex);
        await ConvertAndInsertAsync(metadata, updateMode: false, hasPosition: false, left: 0, top: 0, scale: 1, cancellationToken);
        await _powerPointAdapter.ActivateForEditingAsync(cancellationToken);
    }

    public async Task AcceptEditorFormulaAsync(FormulaEditorAcceptedEventArgs accepted, CancellationToken cancellationToken)
    {
        if (accepted == null)
        {
            throw new ArgumentNullException(nameof(accepted));
        }

        FormulaMetadata metadata = CreateMetadata(accepted.Latex);
        await ConvertAndInsertAsync(
            metadata,
            updateMode: accepted.UpdateMode,
            hasPosition: _hasLoadedShapePosition,
            left: _loadedShapeLeft,
            top: _loadedShapeTop,
            scale: _loadedShapeScale,
            cancellationToken);

        _hasLoadedShapePosition = false;
        if (accepted.UpdateMode)
        {
            _optionsProvider.ResetFormulaDraft();
        }

        await _powerPointAdapter.ActivateForEditingAsync(cancellationToken);
    }

    private async Task ConvertAndInsertAsync(
        FormulaMetadata metadata,
        bool updateMode,
        bool hasPosition,
        float left,
        float top,
        float scale,
        CancellationToken cancellationToken)
    {
        PowerPointPluginSettings settings = PowerPointPluginSettings.Load();
        if (settings.InsertionBackend == FormulaInsertionBackend.Ole)
        {
            _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("OleInsertingStatus"));
            FormulaMetadata oleMetadata = WithRenderEngine(metadata, RenderEngineKind.MathJaxSvg);
            OlePresentationResult presentation = await RenderOlePresentationAsync(oleMetadata, cancellationToken);
            if (updateMode && hasPosition)
            {
                await _powerPointAdapter.DeleteSelectedFormulaAsync(cancellationToken);
                await _powerPointAdapter.InsertOleFormulaObjectAtPositionAsync(oleMetadata, presentation, left, top, scale, cancellationToken);
            }
            else
            {
                await _powerPointAdapter.InsertOleFormulaObjectAsync(oleMetadata, presentation, cancellationToken);
            }

            _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("InsertedStatus"));
            return;
        }

        _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("ConvertingStatus"));
        string responseJson = await _bridgeClient.ConvertLatexAsync(metadata.Latex, display: true, new[] { "png" }, cancellationToken);
        PowerPointConversionResult conversion = PowerPointConversionParser.ParseConversionResponse(responseJson);
        PowerPointRenderedImage image = _imageFileStore.SaveConversionResult(conversion);

        if (updateMode && hasPosition)
        {
            await _powerPointAdapter.DeleteSelectedFormulaAsync(cancellationToken);
            await _powerPointAdapter.InsertFormulaImageAtPositionAsync(image, metadata, left, top, scale, cancellationToken);
        }
        else
        {
            await _powerPointAdapter.InsertFormulaImageAsync(image, metadata, cancellationToken);
        }

        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("InsertedStatus"));
    }

    public async Task LoadSelectedAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        FormulaMetadata selected = await _powerPointAdapter.LoadSelectedFormulaAsync(cancellationToken);
        (_loadedShapeLeft, _loadedShapeTop, _loadedShapeScale) = _powerPointAdapter.GetSelectedShapeFrame();
        _hasLoadedShapePosition = true;
        await _editorSession.OpenForEditAsync(selected, cancellationToken);
        _statusSink.SetCurrentFormula(selected.Latex, updateMode: true);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("LoadedStatus"));
    }

    public async Task DeleteSelectedAsync(CancellationToken cancellationToken)
    {
        int count = await _powerPointAdapter.DeleteSelectedFormulasAsync(cancellationToken);
        string message = count <= 1
            ? PowerPointAddInText.Get("DeletedStatus")
            : PowerPointAddInText.Get("DeletedManyStatus").Replace("{count}", count.ToString(System.Globalization.CultureInfo.InvariantCulture));
        _statusSink.Post(PowerPointStatusKind.Success, message);
    }

    public async Task RecognizeScreenshotAsync(CancellationToken cancellationToken)
    {
        _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("OcrWaitingStatus"));
        try
        {
            string responseJson = await RunScreenshotOcrWithProgressAsync(cancellationToken);
            await ProcessOcrResultAsync(responseJson, cancellationToken);
        }
        catch (InvalidOperationException exc) when (IsOcrAlreadyWaiting(exc.Message))
        {
            await _bridgeClient.CancelScreenshotOcrAsync(CancellationToken.None);
            await Task.Delay(300, CancellationToken.None);
            try
            {
                string responseJson = await RunScreenshotOcrWithProgressAsync(cancellationToken);
                await ProcessOcrResultAsync(responseJson, cancellationToken);
            }
            catch (InvalidOperationException retryExc) when (IsOcrAlreadyWaiting(retryExc.Message))
            {
                _statusSink.Post(PowerPointStatusKind.Error, PowerPointAddInText.Get("BridgeOcrAlreadyWaiting"));
            }
        }
    }

    private Task<string> RunScreenshotOcrWithProgressAsync(CancellationToken cancellationToken)
    {
        return BridgeRecognitionProgress.RunScreenshotOcrAsync(
            _bridgeClient,
            () => _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("OcrRecognizingStatus")),
            cancellationToken);
    }

    private async Task ProcessOcrResultAsync(string responseJson, CancellationToken cancellationToken)
    {
        string latex = PowerPointBridgeRecognitionParser.ParseScreenshotOcrResponse(responseJson);
        if (string.IsNullOrWhiteSpace(latex))
        {
            return;
        }

        FormulaMetadata recognized = CreateMetadata(latex);
        await _editorSession.UpdateDraftIfOpenAsync(recognized, updateMode: false, cancellationToken);
        _statusSink.SetCurrentFormula(recognized.Latex, updateMode: false);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("OcrLoadedStatus"));
    }

    public Task CancelScreenshotOcrAsync(CancellationToken cancellationToken)
    {
        return _bridgeClient.CancelScreenshotOcrAsync(cancellationToken);
    }

    public Task ShowHelpAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        PowerPointPluginHelp.Open();
        _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("HelpStatus"));
        return Task.CompletedTask;
    }

    public Task ShowSettingsAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        PowerPointSettingsWindow.Open();
        _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("SettingsStatus"));
        return Task.CompletedTask;
    }

    private static FormulaMetadata CreateMetadata(string latex)
    {
        string normalizedLatex = string.IsNullOrWhiteSpace(latex) ? DefaultLatex : latex.Trim();
        return new FormulaMetadata(
            new FormulaIdentity("active-presentation", Guid.NewGuid().ToString("N")),
            normalizedLatex,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.Image,
            schemaVersion: 1);
    }

    private static FormulaMetadata CreateEditorDraft()
    {
        return new FormulaMetadata(
            new FormulaIdentity("active-presentation", Guid.NewGuid().ToString("N")),
            string.Empty,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.Image,
            schemaVersion: 1);
    }

    private async Task<OlePresentationResult> RenderOlePresentationAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        var request = new RenderRequest(metadata.Latex, metadata.DisplayMode, RenderEngineKind.MathJaxSvg)
        {
            FontScale = 3.0
        };
        RenderResult intermediate = await _oleIntermediateRenderer.RenderAsync(request, cancellationToken);
        return await _olePresentationPipeline.RenderAsync(
            new OlePresentationRequest(intermediate, OlePresentationKind.EnhancedMetafile),
            cancellationToken);
    }

    private static FormulaMetadata WithRenderEngine(FormulaMetadata metadata, RenderEngineKind renderEngine)
    {
        return new FormulaMetadata(
            metadata.Identity,
            metadata.Latex,
            metadata.DisplayMode,
            metadata.NumberingMode,
            metadata.NumberText,
            renderEngine,
            metadata.SchemaVersion);
    }

    private static bool IsOcrAlreadyWaiting(string message)
    {
        return message.IndexOf("already waiting", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _editorSession.Dispose();
        _bridgeClient.Dispose();
        if (_oleIntermediateRenderer is IDisposable disposableRenderer)
        {
            disposableRenderer.Dispose();
        }

        _commandGate.Dispose();
    }

    private void ThrowIfDisposed()
    {
        if (_disposed)
        {
            throw new ObjectDisposedException(nameof(PowerPointPluginController));
        }
    }
}
