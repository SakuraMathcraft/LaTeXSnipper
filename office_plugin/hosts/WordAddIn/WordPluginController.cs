using System;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordPluginController : IDisposable
{
    private const double OleBaseFontPoints = 10.5;
    private const double MinimumOleFontScale = 0.5;
    private const double MaximumOleFontScale = 5;

    private readonly FormulaEditorSession _editorSession;
    private readonly BridgeClient _bridgeClient;
    private readonly IWordApplicationAdapter _wordAdapter;
    private readonly IWordStatusSink _statusSink;
    private readonly IWordFormulaOptionsProvider _optionsProvider;
    private readonly IFormulaRenderer _oleIntermediateRenderer;
    private readonly OlePresentationPipeline _olePresentationPipeline;
    private readonly SemaphoreSlim _commandGate = new SemaphoreSlim(1, 1);
    private FormulaMetadata? _currentFormula;
    private WordFormulaOptions? _pendingEditorInsertOptions;
    private bool _disposed;

    public WordPluginController(
        FormulaEditorSession editorSession,
        BridgeClient bridgeClient,
        IWordApplicationAdapter wordAdapter,
        IFormulaRenderer oleIntermediateRenderer,
        OlePresentationPipeline olePresentationPipeline,
        IWordStatusSink? statusSink = null,
        IWordFormulaOptionsProvider? optionsProvider = null)
    {
        _editorSession = editorSession ?? throw new ArgumentNullException(nameof(editorSession));
        _bridgeClient = bridgeClient ?? throw new ArgumentNullException(nameof(bridgeClient));
        _wordAdapter = wordAdapter ?? throw new ArgumentNullException(nameof(wordAdapter));
        _oleIntermediateRenderer = oleIntermediateRenderer ?? throw new ArgumentNullException(nameof(oleIntermediateRenderer));
        _olePresentationPipeline = olePresentationPipeline ?? throw new ArgumentNullException(nameof(olePresentationPipeline));
        _statusSink = statusSink ?? NullWordStatusSink.Instance;
        _optionsProvider = optionsProvider ?? DefaultWordFormulaOptionsProvider.Instance;
    }

    public async Task InsertOmmlAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        FormulaMetadata metadata = await CreateMetadataFromDraftAsync(null, _optionsProvider.CurrentLatex, previous: null, cancellationToken);
        await InsertAndRenumberIfNeededAsync(metadata, cancellationToken);
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
                string busyMessage = WordAddInText.Get("WorkingStatus");
                _statusSink.Post(WordStatusKind.Info, busyMessage);
                return FormulaEditorSubmissionResult.Rejected(busyMessage);
            }

            return FormulaEditorSubmissionResult.Accepted();
        }
        catch (OperationCanceledException)
        {
            string message = WordAddInText.Get("CommandTimeoutStatus");
            _statusSink.Post(WordStatusKind.Error, message);
            return FormulaEditorSubmissionResult.Rejected(message);
        }
        catch (Exception exc)
        {
            _statusSink.Post(WordStatusKind.Error, exc.Message);
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

    public async Task InsertFromTaskPaneAsync(CancellationToken cancellationToken)
    {
        await InsertOmmlAsync(cancellationToken);
    }

    public Task InsertInlineAsync(CancellationToken cancellationToken)
    {
        return OpenEditorForInsertAsync(new WordFormulaOptions(display: false, NumberingMode.None, string.Empty), cancellationToken);
    }

    public Task InsertDisplayAsync(CancellationToken cancellationToken)
    {
        return OpenEditorForInsertAsync(new WordFormulaOptions(display: true, NumberingMode.None, string.Empty), cancellationToken);
    }

    public Task InsertNumberedAsync(CancellationToken cancellationToken)
    {
        WordFormulaOptions options = _optionsProvider.GetFormulaOptions();
        NumberingMode numberingMode = options.NumberingMode == NumberingMode.None
            ? NumberingMode.Automatic
            : options.NumberingMode;
        return OpenEditorForInsertAsync(new WordFormulaOptions(display: true, numberingMode, options.ManualNumber), cancellationToken);
    }

    public async Task TestConnectionAsync(CancellationToken cancellationToken)
    {
        await _bridgeClient.ConfigureAsync(cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("ConnectedBridgeStatus"));
    }

    public async Task AcceptEditorFormulaAsync(FormulaEditorAcceptedEventArgs accepted, CancellationToken cancellationToken)
    {
        if (accepted == null)
        {
            throw new ArgumentNullException(nameof(accepted));
        }

        if (accepted.UpdateMode)
        {
            _statusSink.SetCurrentFormula(accepted.Latex, accepted.UpdateMode);
        }

        FormulaIdentity identity = accepted.UpdateMode && accepted.InitialFormula != null
            ? accepted.InitialFormula.Identity
            : new FormulaIdentity("active-document", Guid.NewGuid().ToString("N"));
        FormulaMetadata? previous = accepted.UpdateMode ? accepted.InitialFormula : null;
        FormulaMetadata metadata = accepted.UpdateMode
            ? await CreateMetadataFromDraftAsync(identity, accepted.Latex, previous, cancellationToken)
            : CreateMetadataFromOptions(identity, accepted.Latex, previous, _pendingEditorInsertOptions ?? new WordFormulaOptions(accepted.Display, NumberingMode.None, string.Empty));

        if (accepted.UpdateMode && accepted.InitialFormula != null)
        {
            if (IsSameRenderedFormula(accepted.InitialFormula, metadata))
            {
                _currentFormula = accepted.InitialFormula;
                _pendingEditorInsertOptions = null;
                ResetDraftState(resetOptions: true);
                _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("UnchangedStatus"));
                return;
            }

            await UpdateRenderedFormulaAsync(metadata, cancellationToken);
        }
        else
        {
            await InsertAndRenumberIfNeededAsync(metadata, cancellationToken);
        }

        _currentFormula = metadata;
        _pendingEditorInsertOptions = null;
        ResetDraftState(resetOptions: accepted.UpdateMode);
    }

    public async Task LoadSelectedAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        FormulaMetadata selected = await _wordAdapter.LoadSelectedFormulaAsync(cancellationToken);
        FormulaMetadata initial = IsSameFormula(_currentFormula, selected) ? _currentFormula! : selected;
        await _editorSession.OpenForEditAsync(initial, cancellationToken);
        _pendingEditorInsertOptions = null;
        _currentFormula = selected;
        _optionsProvider.ApplyFormulaMetadata(selected, updateMode: true);
        _statusSink.SetCurrentFormula(selected.Latex, updateMode: true);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("LoadedStatus"));
    }

    public async Task DeleteSelectedAsync(CancellationToken cancellationToken)
    {
        FormulaMetadata metadata = await _wordAdapter.LoadSelectedFormulaAsync(cancellationToken);
        await _wordAdapter.DeleteSelectedFormulaAsync(cancellationToken);
        if (IsSameFormula(_currentFormula, metadata))
        {
            _currentFormula = null;
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("DeletedStatus"));
    }

    public async Task RecognizeScreenshotAsync(CancellationToken cancellationToken)
    {
        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OcrWaitingStatus"));
        try
        {
            string responseJson = await RunScreenshotOcrWithProgressAsync(cancellationToken);
            ProcessOcrResult(responseJson, cancellationToken);
        }
        catch (InvalidOperationException exc) when (IsOcrAlreadyWaiting(exc.Message))
        {
            await _bridgeClient.CancelScreenshotOcrAsync(CancellationToken.None);
            await Task.Delay(300, CancellationToken.None);
            try
            {
                string responseJson = await RunScreenshotOcrWithProgressAsync(cancellationToken);
                ProcessOcrResult(responseJson, cancellationToken);
            }
            catch (InvalidOperationException retryExc) when (IsOcrAlreadyWaiting(retryExc.Message))
            {
                _statusSink.Post(WordStatusKind.Error, WordAddInText.Get("BridgeOcrAlreadyWaiting"));
            }
        }
    }

    private Task<string> RunScreenshotOcrWithProgressAsync(CancellationToken cancellationToken)
    {
        return BridgeRecognitionProgress.RunScreenshotOcrAsync(
            _bridgeClient,
            () => _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OcrRecognizingStatus")),
            cancellationToken);
    }

    private void ProcessOcrResult(string responseJson, CancellationToken cancellationToken)
    {
        string latex = BridgeRecognitionParser.ParseScreenshotOcrResponse(responseJson);
        if (string.IsNullOrWhiteSpace(latex))
        {
            return;
        }

        FormulaMetadata recognized = CreateDefaultFormula(latex);
        _currentFormula = recognized;
        _statusSink.SetCurrentFormula(recognized.Latex, updateMode: false);
        _ = _editorSession.UpdateDraftIfOpenAsync(recognized, updateMode: false, cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("OcrLoadedStatus"));
    }

    private static bool IsOcrAlreadyWaiting(string message)
    {
        return message.IndexOf("already waiting", StringComparison.OrdinalIgnoreCase) >= 0;
    }

    public Task CancelScreenshotOcrAsync(CancellationToken cancellationToken)
    {
        return _bridgeClient.CancelScreenshotOcrAsync(cancellationToken);
    }

    public async Task AutoNumberSelectedAsync(CancellationToken cancellationToken)
    {
        FormulaMetadata selected = await _wordAdapter.LoadSelectedFormulaAsync(cancellationToken);
        if (selected.NumberingMode != NumberingMode.None)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("AlreadyNumberedStatus"));
            return;
        }

        if (selected.DisplayMode != FormulaDisplayMode.Display)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("AutoNumberDisplayOnlyStatus"));
            return;
        }

        FormulaMetadata numbered = WithNumbering(selected, NumberingMode.Automatic, WordAutomaticNumberFormatter.Format(0));
        await UpdateRenderedFormulaAsync(numbered, cancellationToken);
        await _wordAdapter.RenumberAutomaticFormulasAsync(cancellationToken);
        _currentFormula = numbered;
        ResetDraftState(resetOptions: false);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("AutoNumberedStatus"));
    }

    public async Task RenumberAllAsync(CancellationToken cancellationToken)
    {
        int number = await _wordAdapter.RenumberAutomaticFormulasAsync(cancellationToken);

        string message = number == 0
            ? WordAddInText.Get("NoNumberedStatus")
            : WordAddInText.Get("RenumberedStatus").Replace("{count}", number.ToString(CultureInfo.InvariantCulture));
        _statusSink.Post(number == 0 ? WordStatusKind.Info : WordStatusKind.Success, message);
    }

    public Task ShowHelpAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        OfficePluginHelp.Open();
        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("HelpStatus"));
        return Task.CompletedTask;
    }

    public Task ShowSettingsAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        WordSettingsWindow.Open();
        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("SettingsStatus"));
        return Task.CompletedTask;
    }

    private async Task InsertRenderedFormulaAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        await _wordAdapter.ValidateCurrentInsertionTargetAsync(cancellationToken);
        WordPluginSettings settings = WordPluginSettings.Load();
        if (settings.InsertionBackend == FormulaInsertionBackend.Ole)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OleInsertingStatus"));
            FormulaMetadata oleMetadata = WithRenderEngine(metadata, RenderEngineKind.MathJaxSvg);
            OlePresentationResult presentation = await RenderOlePresentationAsync(oleMetadata, cancellationToken);
            await _wordAdapter.InsertOleFormulaObjectAsync(oleMetadata, presentation, IsDisplay(oleMetadata), cancellationToken);
            _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("InsertedStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("ConvertingStatus"));
        string responseJson = await _bridgeClient.ConvertLatexAsync(metadata.Latex, IsDisplay(metadata), new[] { "omml" }, cancellationToken);
        BridgeConversionResult conversion = BridgeConversionParser.ParseConvertLatexResponse(responseJson);
        string ooxml = WordOmmlDocumentBuilder.BuildFlatOpcDocument(conversion.Omml, metadata, IsDisplay(metadata), WordPluginSettings.Load().NumberPlacement);
        await _wordAdapter.InsertManagedEquationAsync(ooxml, metadata, IsDisplay(metadata), cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("InsertedStatus"));
    }

    private async Task UpdateRenderedFormulaAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        WordPluginSettings settings = WordPluginSettings.Load();
        if (settings.InsertionBackend == FormulaInsertionBackend.Ole)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OleInsertingStatus"));
            FormulaMetadata oleMetadata = WithRenderEngine(metadata, RenderEngineKind.MathJaxSvg);
            OlePresentationResult presentation = await RenderOlePresentationAsync(oleMetadata, cancellationToken);
            await _wordAdapter.UpdateOleFormulaObjectAsync(oleMetadata.Identity.EquationId, oleMetadata, presentation, IsDisplay(oleMetadata), cancellationToken);
            _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("UpdatedStatus"));
            return;
        }

        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("ConvertingStatus"));
        string responseJson = await _bridgeClient.ConvertLatexAsync(metadata.Latex, IsDisplay(metadata), new[] { "omml" }, cancellationToken);
        BridgeConversionResult conversion = BridgeConversionParser.ParseConvertLatexResponse(responseJson);
        string ooxml = WordOmmlDocumentBuilder.BuildFlatOpcDocument(conversion.Omml, metadata, IsDisplay(metadata), WordPluginSettings.Load().NumberPlacement);
        string equationOoxml = WordOmmlDocumentBuilder.BuildFlatOpcInlineEquationDocument(conversion.Omml, metadata);
        await _wordAdapter.UpdateFormulaAsync(metadata.Identity.EquationId, ooxml, equationOoxml, metadata, IsDisplay(metadata), cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("UpdatedStatus"));
    }

    private async Task<OlePresentationResult> RenderOlePresentationAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        var request = new RenderRequest(metadata.Latex, metadata.DisplayMode, RenderEngineKind.MathJaxSvg)
        {
            FontScale = GetOleFontScale()
        };
        RenderResult intermediate = await _oleIntermediateRenderer.RenderAsync(request, cancellationToken);
        return await _olePresentationPipeline.RenderAsync(
            new OlePresentationRequest(intermediate, OlePresentationKind.EnhancedMetafile),
            cancellationToken);
    }

    private double GetOleFontScale()
    {
        double fontSize = _wordAdapter.GetCurrentFontSizePoints();
        double scale = fontSize / OleBaseFontPoints;
        return Math.Max(MinimumOleFontScale, Math.Min(MaximumOleFontScale, scale));
    }

    private async Task OpenEditorForInsertAsync(WordFormulaOptions options, CancellationToken cancellationToken)
    {
        _pendingEditorInsertOptions = options;
        FormulaMetadata draft = CreateEditorDraftFromOptions(options);
        await _editorSession.OpenForInsertAsync(draft, cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("EditorReadyStatus"));
    }

    private async Task InsertAndRenumberIfNeededAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        if (metadata.NumberingMode == NumberingMode.Automatic)
        {
            int nextNumber = _wordAdapter.GetNextAutomaticNumber();
            metadata = WithNumbering(metadata, NumberingMode.Automatic, WordAutomaticNumberFormatter.Format(nextNumber));
            _wordAdapter.SetNextAutomaticNumber(nextNumber + 1);
        }

        await InsertRenderedFormulaAsync(metadata, cancellationToken);
        if (metadata.NumberingMode == NumberingMode.Automatic)
        {
            await _wordAdapter.RenumberAutomaticFormulasAsync(cancellationToken);
        }
    }

    private Task<FormulaMetadata> CreateMetadataFromDraftAsync(
        FormulaIdentity? identity,
        string latex,
        FormulaMetadata? previous,
        CancellationToken cancellationToken)
    {
        if (previous != null)
        {
            string normalizedLatex = string.IsNullOrWhiteSpace(latex) ? CreateDefaultLatex() : latex.Trim();
            return Task.FromResult(new FormulaMetadata(
                identity ?? previous.Identity,
                normalizedLatex,
                previous.DisplayMode,
                previous.NumberingMode,
                previous.NumberText,
                previous.RenderEngine,
                previous.SchemaVersion));
        }

        WordFormulaOptions options = _optionsProvider.GetFormulaOptions();
        return Task.FromResult(CreateMetadataFromOptions(identity, latex, previous, options));
    }

    private static FormulaMetadata CreateMetadataFromOptions(
        FormulaIdentity? identity,
        string latex,
        FormulaMetadata? previous,
        WordFormulaOptions options)
    {
        string normalizedLatex = string.IsNullOrWhiteSpace(latex) ? CreateDefaultLatex() : latex.Trim();
        NumberingMode numberingMode = options.NumberingMode;
        string numberText = string.Empty;
        if (numberingMode == NumberingMode.Automatic)
        {
            numberText = previous?.NumberingMode == NumberingMode.Automatic && !string.IsNullOrWhiteSpace(previous.NumberText)
                ? previous.NumberText
                : WordAutomaticNumberFormatter.Format(0);
        }
        else if (numberingMode == NumberingMode.Manual)
        {
            numberText = options.ManualNumber.Trim();
            if (string.IsNullOrWhiteSpace(numberText))
            {
                numberingMode = NumberingMode.None;
            }
        }

        FormulaDisplayMode displayMode = options.Display || numberingMode != NumberingMode.None
            ? FormulaDisplayMode.Display
            : FormulaDisplayMode.Inline;
        FormulaMetadata metadata = new FormulaMetadata(
            identity ?? new FormulaIdentity("active-document", Guid.NewGuid().ToString("N")),
            normalizedLatex,
            displayMode,
            numberingMode,
            numberText,
            RenderEngineKind.Omml,
            schemaVersion: previous?.SchemaVersion ?? 1);
        return metadata;
    }

    private static FormulaMetadata CreateEditorDraftFromOptions(WordFormulaOptions options)
    {
        NumberingMode numberingMode = options.NumberingMode;
        FormulaDisplayMode displayMode = options.Display || numberingMode != NumberingMode.None
            ? FormulaDisplayMode.Display
            : FormulaDisplayMode.Inline;
        return new FormulaMetadata(
            new FormulaIdentity("active-document", Guid.NewGuid().ToString("N")),
            string.Empty,
            displayMode,
            numberingMode,
            options.ManualNumber.Trim(),
            RenderEngineKind.Omml,
            schemaVersion: 1);
    }

    private static FormulaMetadata CreateDefaultFormula(string latex)
    {
        return new FormulaMetadata(
            new FormulaIdentity("active-document", Guid.NewGuid().ToString("N")),
            latex,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.Omml,
            schemaVersion: 1);
    }

    private static FormulaMetadata CreateDraftFormula(string latex)
    {
        return CreateDefaultFormula(string.IsNullOrWhiteSpace(latex) ? CreateDefaultLatex() : latex.Trim());
    }

    private static string CreateDefaultLatex()
    {
        return "e^{i\\pi}+1=0";
    }

    private static bool IsDisplay(FormulaMetadata metadata)
    {
        return metadata.DisplayMode == FormulaDisplayMode.Display;
    }

    private static bool IsSameFormula(FormulaMetadata? left, FormulaMetadata right)
    {
        return left != null && left.Identity.EquationId == right.Identity.EquationId;
    }

    private static bool IsSameRenderedFormula(FormulaMetadata left, FormulaMetadata right)
    {
        return string.Equals(left.Latex.Trim(), right.Latex.Trim(), StringComparison.Ordinal)
            && left.DisplayMode == right.DisplayMode
            && left.NumberingMode == right.NumberingMode
            && string.Equals(left.NumberText.Trim(), right.NumberText.Trim(), StringComparison.Ordinal);
    }

    private static FormulaMetadata WithNumbering(FormulaMetadata metadata, NumberingMode numberingMode, string numberText)
    {
        return new FormulaMetadata(
            metadata.Identity,
            metadata.Latex,
            FormulaDisplayMode.Display,
            numberingMode,
            numberText,
            metadata.RenderEngine,
            metadata.SchemaVersion);
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

    private void ResetDraftState(bool resetOptions)
    {
        _currentFormula = null;
        if (resetOptions)
        {
            _optionsProvider.ResetFormulaDraft();
        }
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
            throw new ObjectDisposedException(nameof(WordPluginController));
        }
    }
}
