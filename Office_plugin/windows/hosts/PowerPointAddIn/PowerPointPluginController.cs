using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Automation;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed partial class PowerPointPluginController : IDisposable
{
    internal const string DefaultLatex = "e^{i\\pi}+1=0";
    private const double ImageHorizontalPaddingPoints = 1.5;
    private const double ImageVerticalPaddingPoints = 0.5;

    private readonly FormulaEditorSession _editorSession;
    private readonly AutomationApiClient _automationClient;
    private readonly IPowerPointApplicationAdapter _powerPointAdapter;
    private readonly IPowerPointStatusSink _statusSink;
    private readonly IPowerPointFormulaOptionsProvider _optionsProvider;
    private readonly PowerPointImageFileStore _imageFileStore;
    private readonly MathJaxSvgRenderer _mathJaxRenderer;
    private readonly OlePresentationPipeline _olePresentationPipeline;
    private readonly SemaphoreSlim _commandGate = new SemaphoreSlim(1, 1);
    private PowerPointFormulaEditTarget? _editorTarget;
    private long _editorTargetGeneration;
    private PowerPointTextInsertionTarget? _textInsertionTarget;
    private long _textInsertionTargetGeneration;
    private bool _disposed;

    public PowerPointPluginController(
        FormulaEditorSession editorSession,
        AutomationApiClient automationClient,
        IPowerPointApplicationAdapter powerPointAdapter,
        MathJaxSvgRenderer mathJaxRenderer,
        OlePresentationPipeline olePresentationPipeline,
        IPowerPointStatusSink? statusSink = null,
        IPowerPointFormulaOptionsProvider? optionsProvider = null,
        PowerPointImageFileStore? imageFileStore = null)
    {
        _editorSession = editorSession ?? throw new ArgumentNullException(nameof(editorSession));
        _automationClient = automationClient ?? throw new ArgumentNullException(nameof(automationClient));
        _powerPointAdapter = powerPointAdapter ?? throw new ArgumentNullException(nameof(powerPointAdapter));
        _mathJaxRenderer = mathJaxRenderer ?? throw new ArgumentNullException(nameof(mathJaxRenderer));
        _olePresentationPipeline = olePresentationPipeline ?? throw new ArgumentNullException(nameof(olePresentationPipeline));
        _statusSink = statusSink ?? NullPowerPointStatusSink.Instance;
        _optionsProvider = optionsProvider ?? DefaultPowerPointFormulaOptionsProvider.Instance;
        _imageFileStore = imageFileStore ?? new PowerPointImageFileStore();
    }

    internal bool TrySelectOleFormulaAtScreenPoint(int x, int y) => _powerPointAdapter.TrySelectOleFormulaAtScreenPoint(x, y);

    public async Task TestConnectionAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        await _automationClient.ConfigureAsync(cancellationToken);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("ConnectedAutomationStatus"));
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
            string message = PowerPointAddInText.GetExceptionMessage(exc);
            _statusSink.Post(PowerPointStatusKind.Error, message);
            return FormulaEditorSubmissionResult.Rejected(message);
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
        if (_editorTarget != null)
        {
            _optionsProvider.ResetFormulaDraft();
        }
        _editorTarget = null;
        _editorTargetGeneration = 0;
        _textInsertionTarget = _powerPointAdapter.CaptureTextInsertionTarget();
        FormulaMetadata draft = CreateEditorDraft(_textInsertionTarget?.FontSizePoints);
        try
        {
            _textInsertionTargetGeneration = await _editorSession.OpenForInsertAsync(draft, cancellationToken);
        }
        catch
        {
            _textInsertionTarget = null;
            _textInsertionTargetGeneration = 0;
            throw;
        }
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("EditorReadyStatus"));
    }

    public async Task InsertFormulaFromTaskPaneAsync(CancellationToken cancellationToken)
    {
        string latex = _optionsProvider.CurrentLatex;
        if (string.IsNullOrWhiteSpace(latex))
        {
            latex = DefaultLatex;
        }

        PowerPointTextInsertionTarget? textTarget = _powerPointAdapter.CaptureTextInsertionTarget();
        FormulaMetadata metadata = CreateMetadata(latex, previous: null, textTarget?.FontSizePoints);
        string statusKey = await SaveFormulaAsync(metadata, null, textTarget, cancellationToken);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get(statusKey));
        await _powerPointAdapter.ActivateForEditingAsync(cancellationToken);
    }

    public async Task AcceptEditorFormulaAsync(FormulaEditorAcceptedEventArgs accepted, CancellationToken cancellationToken)
    {
        if (accepted == null)
        {
            throw new ArgumentNullException(nameof(accepted));
        }

        FormulaMetadata? previous = accepted.UpdateMode ? accepted.InitialFormula : null;
        PowerPointFormulaEditTarget? target = accepted.UpdateMode
            ? GetEditorTarget(accepted)
            : null;
        if (!accepted.UpdateMode && !_editorSession.IsCurrent(accepted.SessionGeneration, accepted.InitialFormula.Identity))
            throw new InvalidOperationException(PowerPointAddInText.Get("EditorSessionChanged"));
        FormulaMetadata metadata = CreateMetadata(accepted.Latex, previous).WithTypography(accepted.Typography);
        PowerPointTextInsertionTarget? textTarget = !accepted.UpdateMode
            && _textInsertionTargetGeneration == accepted.SessionGeneration
                ? _textInsertionTarget
                : null;
        if (previous != null && IsSameRenderedFormula(previous, metadata))
        {
            CompleteEditorSession(accepted.SessionGeneration, target);
            _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("UnchangedStatus"));
            await _powerPointAdapter.ActivateForEditingAsync(cancellationToken);
            return;
        }

        string statusKey = await SaveFormulaAsync(metadata, target, textTarget, cancellationToken);
        if (_editorSession.IsCurrent(accepted.SessionGeneration, accepted.InitialFormula.Identity))
        {
            _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get(statusKey));
        }

        CompleteEditorSession(accepted.SessionGeneration, target);

        await _powerPointAdapter.ActivateForEditingAsync(cancellationToken);
    }

    private async Task<string> SaveFormulaAsync(
        FormulaMetadata metadata,
        PowerPointFormulaEditTarget? target,
        PowerPointTextInsertionTarget? textTarget,
        CancellationToken cancellationToken)
    {
        FormulaInsertionBackend backend = target switch
        {
            null => PowerPointPluginSettings.Load().InsertionBackend,
            { MathType: not null } => FormulaInsertionBackend.MathType,
            { Metadata.RenderEngine: RenderEngineKind.MathJaxSvg } => FormulaInsertionBackend.Ole,
            _ => FormulaInsertionBackend.PowerPointPng
        };
        if (target != null) PostFormulaProgress("UpdatingStatus");

        if (backend == FormulaInsertionBackend.MathType)
        {
            if (target == null) PostFormulaProgress("MathTypeInsertingStatus");
            byte[] compoundFile = await _mathJaxRenderer.CreateMathTypeCompoundFileAsync(metadata, cancellationToken);
            OlePresentationResult presentation = await RenderOlePresentationAsync(metadata, cancellationToken);
            if (target?.MathType is MathTypeFormulaTarget equation)
            {
                await _powerPointAdapter.UpdateMathTypeAsync(equation, compoundFile, presentation, cancellationToken);
                return "UpdatedStatus";
            }
            await _powerPointAdapter.InsertMathTypeAsync(compoundFile, presentation, cancellationToken);
            return "MathTypeInsertedStatus";
        }

        if (textTarget != null)
        {
            string mathMl = await _mathJaxRenderer.ConvertTypographyToMathMlAsync(
                metadata.Latex, FormulaDisplayMode.Inline, metadata.Typography, cancellationToken);
            await _powerPointAdapter.InsertNativeEquationAsync(
                textTarget, mathMl, metadata.Typography.FontSizePoints, cancellationToken);
            return "InsertedNativeEquationStatus";
        }

        if (backend == FormulaInsertionBackend.Ole)
        {
            if (target == null) PostFormulaProgress("OleInsertingStatus");
            FormulaMetadata oleMetadata = WithRenderEngine(metadata, RenderEngineKind.MathJaxSvg);
            OlePresentationResult presentation = await RenderOlePresentationAsync(oleMetadata, cancellationToken);
            if (target != null)
            {
                await _powerPointAdapter.UpdateOleFormulaObjectAsync(target, oleMetadata, presentation, cancellationToken);
                return "UpdatedStatus";
            }
            await _powerPointAdapter.InsertOleFormulaObjectAsync(oleMetadata, presentation, cancellationToken);
            return "InsertedFormulaStatus";
        }

        if (target == null) PostFormulaProgress("ImageInsertingStatus");
        FormulaMetadata imageMetadata = WithRenderEngine(metadata, RenderEngineKind.Image);
        PowerPointRenderedImage image = await RenderImageAsync(imageMetadata, cancellationToken);
        if (target != null)
        {
            await _powerPointAdapter.UpdateFormulaImageAsync(target, image, imageMetadata, cancellationToken);
            return "UpdatedStatus";
        }
        await _powerPointAdapter.InsertFormulaImageAsync(image, imageMetadata, cancellationToken);
        return "InsertedImageStatus";
    }

    private void PostFormulaProgress(string statusKey) =>
        _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get(statusKey));

    public async Task LoadSelectedAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        if (CaptureMathTypeDoubleClick(null) is MathTypeFormulaTarget mathType)
        {
            await LoadMathTypeAsync(mathType, cancellationToken);
            return;
        }
        PowerPointFormulaEditTarget target = await _powerPointAdapter.LoadSelectedFormulaAsync(cancellationToken);
        await OpenEditorForTargetAsync(target, cancellationToken);
    }

    internal MathTypeFormulaTarget? CaptureMathTypeDoubleClick(object? selection) =>
        PowerPointPluginSettings.Load().InsertionBackend == FormulaInsertionBackend.MathType
            ? _powerPointAdapter.CaptureMathTypeFormula(selection) : null;

    internal MathTypeFormulaTarget? CaptureMathTypeDoubleClick(IntPtr window, int x, int y) =>
        PowerPointPluginSettings.Load().InsertionBackend == FormulaInsertionBackend.MathType
            ? _powerPointAdapter.CaptureMathTypeFormulaAtPoint(window, x, y) : null;

    internal async Task LoadMathTypeAsync(MathTypeFormulaTarget target, CancellationToken cancellationToken)
    {
        MathTypeFormulaContent content = await _powerPointAdapter.ReadMathTypeAsync(target, cancellationToken);
        FormulaTypography typography = content.OriginalTypography ?? FormulaTypography.Default.WithFontSize(content.FontSizePoints);
        string latex = content.OriginalLatex ?? await _mathJaxRenderer.ConvertMathTypeToLatexAsync(content, typography, cancellationToken);
        var metadata = new FormulaMetadata(new FormulaIdentity(target.DocumentId, Guid.NewGuid().ToString("N")),
            latex, content.DisplayMode, NumberingMode.None, string.Empty, RenderEngineKind.MathJaxSvg,
            FormulaMetadata.CurrentSchemaVersion, typography);
        await OpenEditorForTargetAsync(new PowerPointFormulaEditTarget(metadata, target.Document, target), cancellationToken);
    }

    private async Task OpenEditorForTargetAsync(PowerPointFormulaEditTarget target, CancellationToken cancellationToken)
    {
        if (_editorTarget != null)
        {
            _optionsProvider.ResetFormulaDraft();
        }

        _editorTarget = target;
        _editorTargetGeneration = 0;
        _textInsertionTarget = null;
        _textInsertionTargetGeneration = 0;
        _statusSink.SetCurrentFormula(target.Metadata.Latex, updateMode: true);
        try
        {
            long generation = await _editorSession.OpenForEditAsync(target.Metadata, cancellationToken).ConfigureAwait(true);
            if (ReferenceEquals(_editorTarget, target)
                && _editorSession.IsCurrent(generation, target.Metadata.Identity))
            {
                _editorTargetGeneration = generation;
            }
        }
        catch
        {
            if (ReferenceEquals(_editorTarget, target))
            {
                _optionsProvider.ResetFormulaDraft();
                _editorTarget = null;
                _editorTargetGeneration = 0;
            }

            throw;
        }

        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("LoadedStatus"));
    }

    public void CancelEditorFormula(long sessionGeneration)
    {
        if (!_editorSession.Complete(sessionGeneration))
        {
            return;
        }

        if (_editorTargetGeneration == sessionGeneration)
        {
            _optionsProvider.ResetFormulaDraft();
            _editorTarget = null;
            _editorTargetGeneration = 0;
        }
        if (_textInsertionTargetGeneration == sessionGeneration)
        {
            _textInsertionTarget = null;
            _textInsertionTargetGeneration = 0;
        }
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
            ProcessOcrResult(responseJson);
        }
        catch (InvalidOperationException exc) when (IsOcrAlreadyWaiting(exc.Message))
        {
            await _automationClient.CancelScreenshotOcrAsync(CancellationToken.None);
            await Task.Delay(300, CancellationToken.None);
            try
            {
                string responseJson = await RunScreenshotOcrWithProgressAsync(cancellationToken);
                ProcessOcrResult(responseJson);
            }
            catch (InvalidOperationException retryExc) when (IsOcrAlreadyWaiting(retryExc.Message))
            {
                _statusSink.Post(PowerPointStatusKind.Error, PowerPointAddInText.Get("AutomationOcrAlreadyWaiting"));
            }
        }
    }

    private Task<string> RunScreenshotOcrWithProgressAsync(CancellationToken cancellationToken)
    {
        return AutomationRecognitionProgress.RunScreenshotOcrAsync(
            _automationClient,
            () => _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("OcrRecognizingStatus")),
            cancellationToken);
    }

    private void ProcessOcrResult(string responseJson)
    {
        string latex = PowerPointAutomationRecognitionParser.ParseScreenshotOcrResponse(responseJson);
        if (string.IsNullOrWhiteSpace(latex))
        {
            return;
        }

        _statusSink.SetCurrentFormula(latex, updateMode: false);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("OcrLoadedStatus"));
    }

    public Task CancelScreenshotOcrAsync(CancellationToken cancellationToken)
    {
        return _automationClient.CancelScreenshotOcrAsync(cancellationToken);
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

    private FormulaMetadata CreateMetadata(string latex, FormulaMetadata? previous, double? hostFontSizePoints = null)
    {
        string normalizedLatex = string.IsNullOrWhiteSpace(latex)
            ? DefaultLatex
            : MathLiveLatexStyleNormalizer.NormalizeLatex(latex.Trim());
        PowerPointPluginSettings settings = PowerPointPluginSettings.Load();
        return new FormulaMetadata(
            previous?.Identity ?? new FormulaIdentity(_powerPointAdapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
            normalizedLatex,
            previous?.DisplayMode ?? FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            previous?.RenderEngine ?? RenderEngineKind.Image,
            schemaVersion: FormulaMetadata.CurrentSchemaVersion,
            previous?.Typography ?? settings.TypographyDefaults.ResolveForNewFormula(hostFontSizePoints ?? _powerPointAdapter.GetCurrentFontSizePoints()).Typography);
    }

    private FormulaMetadata CreateEditorDraft(double? hostFontSizePoints)
    {
        PowerPointPluginSettings settings = PowerPointPluginSettings.Load();
        return new FormulaMetadata(
            new FormulaIdentity(_powerPointAdapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
            string.Empty,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.Image,
            schemaVersion: FormulaMetadata.CurrentSchemaVersion,
            settings.TypographyDefaults.ResolveForNewFormula(hostFontSizePoints ?? _powerPointAdapter.GetCurrentFontSizePoints()).Typography);
    }

    private async Task<OlePresentationResult> RenderOlePresentationAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        var request = new RenderRequest(metadata.Latex, metadata.DisplayMode, RenderEngineKind.MathJaxSvg, metadata.Typography);
        RenderResult intermediate = await _mathJaxRenderer.RenderAsync(request, cancellationToken);
        return await _olePresentationPipeline.RenderAsync(
            new OlePresentationRequest(intermediate, OlePresentationKind.EnhancedMetafile),
            cancellationToken);
    }

    private async Task<PowerPointRenderedImage> RenderImageAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        var request = new RenderRequest(metadata.Latex, FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg, metadata.Typography);
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
            metadata.Typography);
    }

    private static bool IsSameRenderedFormula(FormulaMetadata left, FormulaMetadata right)
    {
        return string.Equals(left.Latex.Trim(), right.Latex.Trim(), StringComparison.Ordinal)
            && left.DisplayMode == right.DisplayMode
            && left.Typography.Equals(right.Typography);
    }

    private PowerPointFormulaEditTarget GetEditorTarget(FormulaEditorAcceptedEventArgs accepted)
    {
        if (_editorTarget == null
            || _editorTargetGeneration != accepted.SessionGeneration
            || !string.Equals(
                _editorTarget.Metadata.Identity.EquationId,
                accepted.InitialFormula.Identity.EquationId,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaRequired"));
        }

        return _editorTarget;
    }

    private void CompleteEditorSession(long sessionGeneration, PowerPointFormulaEditTarget? target)
    {
        if (!_editorSession.Complete(sessionGeneration))
        {
            return;
        }

        if (target != null)
        {
            _optionsProvider.ResetFormulaDraft();
        }

        if (_editorTargetGeneration == sessionGeneration)
        {
            _editorTarget = null;
            _editorTargetGeneration = 0;
        }
        if (_textInsertionTargetGeneration == sessionGeneration)
        {
            _textInsertionTarget = null;
            _textInsertionTargetGeneration = 0;
        }
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
        _automationClient.Dispose();
        _mathJaxRenderer.Dispose();
        (_powerPointAdapter as IDisposable)?.Dispose();
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
