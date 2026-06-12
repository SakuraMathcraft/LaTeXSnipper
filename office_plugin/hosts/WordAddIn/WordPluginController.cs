using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class WordPluginController : IDisposable
{
    private const double OleBaseFontPoints = 10.5;
    private const double MinimumOleFontScale = 0.5;
    private const double MaximumOleFontScale = 5;

    private readonly FormulaEditorSession _editorSession;
    private readonly BridgeClient _bridgeClient;
    private readonly IWordApplicationAdapter _wordAdapter;
    private readonly IWordStatusSink _statusSink;
    private readonly IWordFormulaOptionsProvider _optionsProvider;
    private readonly MathJaxSvgRenderer _mathJaxRenderer;
    private readonly MathMlToOmmlConverter _ommlConverter;
    private readonly OlePresentationPipeline _olePresentationPipeline;
    private readonly SemaphoreSlim _commandGate = new SemaphoreSlim(1, 1);
    private FormulaMetadata? _currentFormula;
    private WordFormulaOptions? _pendingEditorInsertOptions;
    private bool _disposed;

    private sealed class PreparedWordFormula
    {
        public PreparedWordFormula(FormulaMetadata metadata, bool display, OlePresentationResult? olePresentation, string? ooxml, string? equationOoxml)
        {
            Metadata = metadata;
            Display = display;
            OlePresentation = olePresentation;
            Ooxml = ooxml;
            EquationOoxml = equationOoxml;
        }

        public FormulaMetadata Metadata { get; }

        public bool Display { get; }

        public OlePresentationResult? OlePresentation { get; }

        public string? Ooxml { get; }

        public string? EquationOoxml { get; }
    }

    public WordPluginController(
        FormulaEditorSession editorSession,
        BridgeClient bridgeClient,
        IWordApplicationAdapter wordAdapter,
        MathJaxSvgRenderer mathJaxRenderer,
        OlePresentationPipeline olePresentationPipeline,
        IWordStatusSink? statusSink = null,
        IWordFormulaOptionsProvider? optionsProvider = null,
        MathMlToOmmlConverter? ommlConverter = null)
    {
        _editorSession = editorSession ?? throw new ArgumentNullException(nameof(editorSession));
        _bridgeClient = bridgeClient ?? throw new ArgumentNullException(nameof(bridgeClient));
        _wordAdapter = wordAdapter ?? throw new ArgumentNullException(nameof(wordAdapter));
        _mathJaxRenderer = mathJaxRenderer ?? throw new ArgumentNullException(nameof(mathJaxRenderer));
        _ommlConverter = ommlConverter ?? new MathMlToOmmlConverter();
        _olePresentationPipeline = olePresentationPipeline ?? throw new ArgumentNullException(nameof(olePresentationPipeline));
        _statusSink = statusSink ?? NullWordStatusSink.Instance;
        _optionsProvider = optionsProvider ?? DefaultWordFormulaOptionsProvider.Instance;
    }

    public async Task InsertOmmlAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        FormulaMetadata metadata = await CreateMetadataFromDraftAsync(null, _optionsProvider.CurrentLatex, previous: null, cancellationToken);
        await InsertAndRenumberIfNeededAsync(metadata, cancellationToken);
        await _wordAdapter.ActivateForEditingAsync(cancellationToken);
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
        await _mathJaxRenderer.WarmUpAsync(cancellationToken);
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
                await _wordAdapter.ActivateForEditingAsync(cancellationToken);
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
        await _wordAdapter.ActivateForEditingAsync(cancellationToken);
    }

    public async Task LoadSelectedAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        FormulaMetadata selected = await _wordAdapter.LoadSelectedFormulaAsync(cancellationToken);
        await _editorSession.OpenForEditAsync(selected, cancellationToken);
        _pendingEditorInsertOptions = null;
        _currentFormula = selected;
        _optionsProvider.ApplyFormulaMetadata(selected, updateMode: true);
        _statusSink.SetCurrentFormula(selected.Latex, updateMode: true);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("LoadedStatus"));
    }

    public async Task DeleteSelectedAsync(CancellationToken cancellationToken)
    {
        IReadOnlyList<string> deletedEquationIds;
        using (_wordAdapter.BeginUndoRecord())
        {
            deletedEquationIds = await _wordAdapter.DeleteSelectedFormulaAsync(cancellationToken);
        }

        if (_currentFormula != null && deletedEquationIds.Contains(_currentFormula.Identity.EquationId))
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
        await UpdateRenderedFormulaAndRenumberAsync(numbered, cancellationToken);
        _currentFormula = numbered;
        ResetDraftState(resetOptions: false);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("AutoNumberedStatus"));
    }

    public async Task RenumberAllAsync(CancellationToken cancellationToken)
    {
        int number;
        using (_wordAdapter.BeginUndoRecord())
        {
            number = await _wordAdapter.RenumberAutomaticFormulasAsync(cancellationToken);
        }

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
        WordSettingsWindow.Open(() =>
        {
            _ = TryRunCommandAsync(
                ct => _wordAdapter.ApplyNumberingBoundaryVisibilityAsync(ct),
                CancellationToken.None);
        });
        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("SettingsStatus"));
        return Task.CompletedTask;
    }

    private async Task InsertRenderedFormulaAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        await _wordAdapter.ValidateCurrentInsertionTargetAsync(cancellationToken);
        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(metadata, includeEquationOoxml: false, cancellationToken);
        using (_wordAdapter.BeginUndoRecord())
        {
            await InsertPreparedFormulaAsync(prepared, cancellationToken);
        }
    }

    private async Task UpdateRenderedFormulaAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(metadata, includeEquationOoxml: true, cancellationToken);
        using (_wordAdapter.BeginUndoRecord())
        {
            await UpdatePreparedFormulaAsync(prepared, cancellationToken);
        }
    }

    private async Task UpdateRenderedFormulaAndRenumberAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(metadata, includeEquationOoxml: true, cancellationToken);
        using (_wordAdapter.BeginUndoRecord())
        {
            await UpdatePreparedFormulaAsync(prepared, cancellationToken);
            await _wordAdapter.RenumberAutomaticFormulasAsync(cancellationToken);
        }
    }

    private async Task<PreparedWordFormula> PrepareRenderedFormulaAsync(
        FormulaMetadata metadata,
        bool includeEquationOoxml,
        CancellationToken cancellationToken,
        FormulaInsertionBackend? backendOverride = null,
        bool reportProgress = true)
    {
        WordPluginSettings settings = WordPluginSettings.Load();
        FormulaInsertionBackend backend = backendOverride ?? settings.InsertionBackend;
        string renderedLatex = BuildFormattedLatex(metadata);
        if (backend == FormulaInsertionBackend.Ole)
        {
            if (reportProgress)
            {
                _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OleInsertingStatus"));
            }

            FormulaMetadata oleMetadata = WithRenderEngine(metadata, RenderEngineKind.MathJaxSvg);
            OlePresentationResult presentation = await RenderOlePresentationAsync(oleMetadata, renderedLatex, cancellationToken);
            return new PreparedWordFormula(oleMetadata, IsDisplay(oleMetadata), presentation, null, null);
        }

        if (reportProgress)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("ConvertingStatus"));
        }
        string mathMl = await _mathJaxRenderer.ConvertToMathMlAsync(renderedLatex, metadata.DisplayMode, cancellationToken);
        string omml = _ommlConverter.Convert(mathMl);
        string ooxml = WordOmmlDocumentBuilder.BuildFlatOpcDocument(omml, metadata, IsDisplay(metadata), settings.NumberPlacement);
        string? equationOoxml = includeEquationOoxml ? WordOmmlDocumentBuilder.BuildFlatOpcInlineEquationDocument(omml, metadata) : null;
        return new PreparedWordFormula(metadata, IsDisplay(metadata), null, ooxml, equationOoxml);
    }

    private async Task InsertPreparedFormulaAsync(PreparedWordFormula prepared, CancellationToken cancellationToken)
    {
        if (prepared.OlePresentation != null)
        {
            await _wordAdapter.InsertOleFormulaObjectAsync(prepared.Metadata, prepared.OlePresentation, prepared.Display, cancellationToken);
            _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("InsertedStatus"));
            return;
        }

        await _wordAdapter.InsertManagedEquationAsync(prepared.Ooxml!, prepared.Metadata, prepared.Display, cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("InsertedStatus"));
    }

    private async Task UpdatePreparedFormulaAsync(PreparedWordFormula prepared, CancellationToken cancellationToken)
    {
        if (prepared.OlePresentation != null)
        {
            await _wordAdapter.UpdateOleFormulaObjectAsync(prepared.Metadata.Identity.EquationId, prepared.Metadata, prepared.OlePresentation, prepared.Display, cancellationToken);
            _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("UpdatedStatus"));
            return;
        }

        await _wordAdapter.UpdateFormulaAsync(prepared.Metadata.Identity.EquationId, prepared.Ooxml!, prepared.EquationOoxml!, prepared.Metadata, prepared.Display, cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("UpdatedStatus"));
    }

    private async Task<OlePresentationResult> RenderOlePresentationAsync(
        FormulaMetadata metadata,
        string renderedLatex,
        CancellationToken cancellationToken)
    {
        var request = new RenderRequest(renderedLatex, metadata.DisplayMode, RenderEngineKind.MathJaxSvg)
        {
            FontScale = GetOleFontScale() * metadata.FontScale
        };
        RenderResult intermediate = await _mathJaxRenderer.RenderAsync(request, cancellationToken);
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
        int nextNumber = 0;
        if (metadata.NumberingMode == NumberingMode.Automatic)
        {
            nextNumber = _wordAdapter.GetNextAutomaticNumber();
            metadata = WithNumbering(metadata, NumberingMode.Automatic, WordAutomaticNumberFormatter.Format(nextNumber));
        }

        await _wordAdapter.ValidateCurrentInsertionTargetAsync(cancellationToken);
        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(metadata, includeEquationOoxml: false, cancellationToken);
        using (_wordAdapter.BeginUndoRecord())
        {
            await InsertPreparedFormulaAsync(prepared, cancellationToken);
            if (metadata.NumberingMode == NumberingMode.Automatic)
            {
                _wordAdapter.SetNextAutomaticNumber(nextNumber + 1);
            }
        }
    }

    private static string BuildFormattedLatex(FormulaMetadata metadata)
    {
        string latex = metadata.Latex;
        switch (metadata.FontStyle)
        {
            case FormulaFontStyle.TeX:
                break;
            case FormulaFontStyle.RomanUpright:
                latex = "\\mathrm{" + latex + "}";
                break;
            case FormulaFontStyle.Bold:
                latex = "\\boldsymbol{" + latex + "}";
                break;
            case FormulaFontStyle.Italic:
                latex = "\\mathit{" + latex + "}";
                break;
        }

        if (!string.Equals(metadata.FontColor, "#000000", StringComparison.OrdinalIgnoreCase))
        {
            latex = "\\color{" + metadata.FontColor + "}{" + latex + "}";
        }

        return latex;
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
                previous.SchemaVersion,
                previous.FontColor,
                previous.FontStyle,
                previous.FontScale));
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
        WordPluginSettings settings = WordPluginSettings.Load();
        FormulaMetadata metadata = new FormulaMetadata(
            identity ?? new FormulaIdentity("active-document", Guid.NewGuid().ToString("N")),
            normalizedLatex,
            displayMode,
            numberingMode,
            numberText,
            RenderEngineKind.Omml,
            schemaVersion: previous?.SchemaVersion ?? 1,
            previous?.FontColor ?? settings.FormulaColor,
            previous?.FontStyle ?? settings.FormulaFontStyle,
            previous?.FontScale ?? 1);
        return metadata;
    }

    private static FormulaMetadata CreateEditorDraftFromOptions(WordFormulaOptions options)
    {
        NumberingMode numberingMode = options.NumberingMode;
        FormulaDisplayMode displayMode = options.Display || numberingMode != NumberingMode.None
            ? FormulaDisplayMode.Display
            : FormulaDisplayMode.Inline;
        WordPluginSettings settings = WordPluginSettings.Load();
        return new FormulaMetadata(
            new FormulaIdentity("active-document", Guid.NewGuid().ToString("N")),
            string.Empty,
            displayMode,
            numberingMode,
            options.ManualNumber.Trim(),
            RenderEngineKind.Omml,
            schemaVersion: 1,
            settings.FormulaColor,
            settings.FormulaFontStyle,
            fontScale: 1);
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
            metadata.SchemaVersion,
            metadata.FontColor,
            metadata.FontStyle,
            metadata.FontScale);
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
        _mathJaxRenderer.Dispose();

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
