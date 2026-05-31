using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointPluginController
{
    internal const string DefaultLatex = "e^{i\\pi}+1=0";

    private readonly FormulaEditorSession _editorSession;
    private readonly BridgeClient _bridgeClient;
    private readonly IPowerPointApplicationAdapter _powerPointAdapter;
    private readonly IPowerPointStatusSink _statusSink;
    private readonly IPowerPointFormulaOptionsProvider _optionsProvider;
    private readonly PowerPointImageFileStore _imageFileStore;
    private float _loadedShapeLeft;
    private float _loadedShapeTop;
    private bool _hasLoadedShapePosition;

    public PowerPointPluginController(
        FormulaEditorSession editorSession,
        BridgeClient bridgeClient,
        IPowerPointApplicationAdapter powerPointAdapter,
        IPowerPointStatusSink? statusSink = null,
        IPowerPointFormulaOptionsProvider? optionsProvider = null,
        PowerPointImageFileStore? imageFileStore = null)
    {
        _editorSession = editorSession ?? throw new ArgumentNullException(nameof(editorSession));
        _bridgeClient = bridgeClient ?? throw new ArgumentNullException(nameof(bridgeClient));
        _powerPointAdapter = powerPointAdapter ?? throw new ArgumentNullException(nameof(powerPointAdapter));
        _statusSink = statusSink ?? NullPowerPointStatusSink.Instance;
        _optionsProvider = optionsProvider ?? DefaultPowerPointFormulaOptionsProvider.Instance;
        _imageFileStore = imageFileStore ?? new PowerPointImageFileStore();
    }

    public async Task TestConnectionAsync(CancellationToken cancellationToken)
    {
        await _bridgeClient.ConfigureAsync(cancellationToken);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("ConnectedBridgeStatus"));
    }

    public async Task InsertFormulaAsync(CancellationToken cancellationToken)
    {
        _hasLoadedShapePosition = false;
        FormulaMetadata draft = CreateMetadata(string.Empty);
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
        await ConvertAndInsertAsync(metadata, updateMode: false, hasPosition: false, left: 0, top: 0, cancellationToken);
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
            cancellationToken);

        _hasLoadedShapePosition = false;
        if (accepted.UpdateMode)
        {
            _optionsProvider.ResetFormulaDraft();
        }
    }

    private async Task ConvertAndInsertAsync(
        FormulaMetadata metadata,
        bool updateMode,
        bool hasPosition,
        float left,
        float top,
        CancellationToken cancellationToken)
    {
        _statusSink.Post(PowerPointStatusKind.Info, PowerPointAddInText.Get("ConvertingStatus"));
        string responseJson = await _bridgeClient.ConvertLatexAsync(metadata.Latex, display: true, new[] { "png" }, cancellationToken);
        PowerPointConversionResult conversion = PowerPointConversionParser.ParseConversionResponse(responseJson);
        PowerPointRenderedImage image = _imageFileStore.SaveConversionResult(conversion);

        if (updateMode && hasPosition)
        {
            await _powerPointAdapter.DeleteSelectedFormulaAsync(cancellationToken);
            await _powerPointAdapter.InsertFormulaImageAtPositionAsync(image, metadata, left, top, cancellationToken);
        }
        else
        {
            await _powerPointAdapter.InsertFormulaImageAsync(image, metadata, cancellationToken);
        }

        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("InsertedStatus"));
    }

    public async Task LoadSelectedAsync(CancellationToken cancellationToken)
    {
        FormulaMetadata selected = await _powerPointAdapter.LoadSelectedFormulaAsync(cancellationToken);
        (_loadedShapeLeft, _loadedShapeTop) = _powerPointAdapter.GetSelectedShapePosition();
        _hasLoadedShapePosition = true;
        await _editorSession.OpenForEditAsync(selected, cancellationToken);
        _statusSink.SetCurrentFormula(selected.Latex, updateMode: true);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("LoadedStatus"));
    }

    public async Task DeleteSelectedAsync(CancellationToken cancellationToken)
    {
        await _powerPointAdapter.DeleteSelectedFormulaAsync(cancellationToken);
        _statusSink.Post(PowerPointStatusKind.Success, PowerPointAddInText.Get("DeletedStatus"));
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

    private static bool IsOcrAlreadyWaiting(string message)
    {
        return message.IndexOf("already waiting", StringComparison.OrdinalIgnoreCase) >= 0;
    }
}
