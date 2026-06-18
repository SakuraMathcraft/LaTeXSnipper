using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed partial class PowerPointPluginController : IDisposable
{
    internal const string DefaultLatex = "e^{i\\pi}+1=0";
    private const double InitialFormulaScale = 2.5;
    private const double ImageHorizontalPaddingPoints = 1.5;
    private const double ImageVerticalPaddingPoints = 0.5;

    private readonly FormulaEditorSession _editorSession;
    private readonly BridgeClient _bridgeClient;
    private readonly IPowerPointApplicationAdapter _powerPointAdapter;
    private readonly IPowerPointStatusSink _statusSink;
    private readonly IPowerPointFormulaOptionsProvider _optionsProvider;
    private readonly PowerPointImageFileStore _imageFileStore;
    private readonly MathJaxSvgRenderer _mathJaxRenderer;
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
        MathJaxSvgRenderer mathJaxRenderer,
        OlePresentationPipeline olePresentationPipeline,
        IPowerPointStatusSink? statusSink = null,
        IPowerPointFormulaOptionsProvider? optionsProvider = null,
        PowerPointImageFileStore? imageFileStore = null)
    {
        _editorSession = editorSession ?? throw new ArgumentNullException(nameof(editorSession));
        _bridgeClient = bridgeClient ?? throw new ArgumentNullException(nameof(bridgeClient));
        _powerPointAdapter = powerPointAdapter ?? throw new ArgumentNullException(nameof(powerPointAdapter));
        _mathJaxRenderer = mathJaxRenderer ?? throw new ArgumentNullException(nameof(mathJaxRenderer));
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
        await _mathJaxRenderer.WarmUpAsync(cancellationToken);
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

        FormulaMetadata metadata = CreateMetadata(latex, previous: null);
        await ConvertAndInsertAsync(metadata, updateMode: false, hasPosition: false, left: 0, top: 0, scale: 1, cancellationToken);
        await _powerPointAdapter.ActivateForEditingAsync(cancellationToken);
    }

    public async Task AcceptEditorFormulaAsync(FormulaEditorAcceptedEventArgs accepted, CancellationToken cancellationToken)
    {
        if (accepted == null)
        {
            throw new ArgumentNullException(nameof(accepted));
        }

        FormulaMetadata? previous = accepted.UpdateMode ? accepted.InitialFormula : null;
        FormulaMetadata metadata = CreateMetadata(accepted.Latex, previous, accepted.FontStyle);
        if (previous != null && IsSameRenderedFormula(previous, metadata))
        {
            _hasLoadedShapePosition = false;
            _optionsProvider.ResetFormulaDraft();
            _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("UnchangedStatus"));
            await _powerPointAdapter.ActivateForEditingAsync(cancellationToken);
            return;
        }

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

            _statusSink.Post(
                PowerPointStatusKind.Success,
                PowerPointAddInText.Get(updateMode ? "UpdatedStatus" : "InsertedFormulaStatus"));
            return;
        }

        _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("ConvertingStatus"));
        FormulaMetadata imageMetadata = WithRenderEngine(metadata, RenderEngineKind.Image);
        PowerPointRenderedImage image = await RenderImageAsync(imageMetadata, cancellationToken);

        if (updateMode && hasPosition)
        {
            await _powerPointAdapter.DeleteSelectedFormulaAsync(cancellationToken);
            await _powerPointAdapter.InsertFormulaImageAtPositionAsync(image, imageMetadata, left, top, scale, cancellationToken);
        }
        else
        {
            await _powerPointAdapter.InsertFormulaImageAsync(image, imageMetadata, cancellationToken);
        }

        _statusSink.Post(
            PowerPointStatusKind.Success,
            PowerPointAddInText.Get(updateMode ? "UpdatedStatus" : "InsertedImageStatus"));
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

        FormulaMetadata recognized = CreateMetadata(latex, previous: null);
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

    private static FormulaMetadata CreateMetadata(string latex, FormulaMetadata? previous, FormulaFontStyle? acceptedFontStyle = null)
    {
        string normalizedLatex = string.IsNullOrWhiteSpace(latex) ? DefaultLatex : latex.Trim();
        PowerPointPluginSettings settings = PowerPointPluginSettings.Load();
        return new FormulaMetadata(
            previous?.Identity ?? new FormulaIdentity("active-presentation", Guid.NewGuid().ToString("N")),
            normalizedLatex,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            previous?.RenderEngine ?? RenderEngineKind.Image,
            schemaVersion: previous?.SchemaVersion ?? 1,
            previous?.FontColor ?? settings.FormulaColor,
            acceptedFontStyle ?? previous?.FontStyle ?? settings.FormulaFontStyle,
            previous?.FontScale ?? settings.FormulaFontScale);
    }

    private static FormulaMetadata CreateEditorDraft()
    {
        PowerPointPluginSettings settings = PowerPointPluginSettings.Load();
        return new FormulaMetadata(
            new FormulaIdentity("active-presentation", Guid.NewGuid().ToString("N")),
            string.Empty,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.Image,
            schemaVersion: 1,
            settings.FormulaColor,
            settings.FormulaFontStyle,
            settings.FormulaFontScale);
    }

    private async Task<OlePresentationResult> RenderOlePresentationAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        var request = new RenderRequest(BuildFormattedLatex(metadata), metadata.DisplayMode, RenderEngineKind.MathJaxSvg)
        {
            FontScale = InitialFormulaScale * metadata.FontScale
        };
        RenderResult intermediate = await _mathJaxRenderer.RenderAsync(request, cancellationToken);
        return await _olePresentationPipeline.RenderAsync(
            new OlePresentationRequest(intermediate, OlePresentationKind.EnhancedMetafile),
            cancellationToken);
    }

    private async Task<PowerPointRenderedImage> RenderImageAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        var request = new RenderRequest(BuildFormattedLatex(metadata), FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg)
        {
            FontScale = InitialFormulaScale * metadata.FontScale
        };
        RenderResult svg = await _mathJaxRenderer.RenderAsync(request, cancellationToken);
        byte[] png = SvgPngRasterizer.Rasterize(
            svg,
            cancellationToken,
            horizontalPaddingPoints: ImageHorizontalPaddingPoints,
            verticalPaddingPoints: ImageVerticalPaddingPoints);
        return _imageFileStore.SavePng(
            png,
            svg.WidthPoints + ImageHorizontalPaddingPoints * 2,
            svg.HeightPoints + ImageVerticalPaddingPoints * 2);
    }

    private static string BuildFormattedLatex(FormulaMetadata metadata)
    {
        string latex = MathLiveLatexStyleNormalizer.ApplyRenderFontStyle(metadata.Latex, metadata.FontStyle);
        return string.Equals(metadata.FontColor, "#000000", StringComparison.OrdinalIgnoreCase)
            ? latex
            : "\\color{" + metadata.FontColor + "}{" + latex + "}";
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
            metadata.SchemaVersion,
            metadata.FontColor,
            metadata.FontStyle,
            metadata.FontScale);
    }

    private static bool IsSameRenderedFormula(FormulaMetadata left, FormulaMetadata right)
    {
        return string.Equals(left.Latex.Trim(), right.Latex.Trim(), StringComparison.Ordinal)
            && left.DisplayMode == right.DisplayMode
            && string.Equals(left.FontColor, right.FontColor, StringComparison.OrdinalIgnoreCase)
            && left.FontStyle == right.FontStyle
            && Math.Abs(left.FontScale - right.FontScale) <= 0.001;
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
        _mathJaxRenderer.Dispose();

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
