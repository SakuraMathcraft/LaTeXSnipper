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
    private WordFormulaOptions? _pendingEditorInsertOptions;
    private WordFormulaEditTarget? _editorTarget;
    private long _editorTargetGeneration;
    private bool _disposed;

    private sealed class PreparedWordFormula
    {
        public PreparedWordFormula(
            FormulaMetadata metadata,
            bool display,
            OlePresentationResult? olePresentation,
            string? ooxml,
            string? equationOoxml,
            string? equationContentOoxml)
        {
            Metadata = metadata;
            Display = display;
            OlePresentation = olePresentation;
            Ooxml = ooxml;
            EquationOoxml = equationOoxml;
            EquationContentOoxml = equationContentOoxml;
        }

        public FormulaMetadata Metadata { get; }

        public bool Display { get; }

        public OlePresentationResult? OlePresentation { get; }

        public string? Ooxml { get; }

        public string? EquationOoxml { get; }

        public string? EquationContentOoxml { get; }
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
        FormulaMetadata metadata = CreateMetadataFromDraft(
            null,
            _optionsProvider.CurrentLatex,
            previous: null);
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

        WordFormulaEditTarget? target = accepted.UpdateMode
            ? GetEditorTarget(accepted)
            : null;
        FormulaIdentity identity = target != null
            ? target.Metadata.Identity
            : new FormulaIdentity(_wordAdapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N"));
        FormulaMetadata? previous = accepted.UpdateMode ? accepted.InitialFormula : null;
        FormulaMetadata metadata = accepted.UpdateMode
            ? CreateMetadataFromDraft(identity, accepted.Latex, previous)
            : CreateMetadataFromOptions(identity, accepted.Latex, previous, _pendingEditorInsertOptions ?? new WordFormulaOptions(accepted.Display, NumberingMode.None, string.Empty));

        if (accepted.UpdateMode)
        {
            if (IsSameRenderedFormula(accepted.InitialFormula, metadata))
            {
                _pendingEditorInsertOptions = null;
                CompleteEditorSession(accepted.SessionGeneration, target);
                _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("UnchangedStatus"));
                await _wordAdapter.ActivateForEditingAsync(cancellationToken);
                return;
            }

            await UpdateRenderedFormulaAsync(metadata, target, cancellationToken, reportStatus: false);
        }
        else
        {
            await InsertAndRenumberIfNeededAsync(metadata, cancellationToken, reportStatus: false);
        }

        _pendingEditorInsertOptions = null;
        if (_editorSession.IsCurrent(accepted.SessionGeneration, accepted.InitialFormula.Identity))
        {
            string statusKey = accepted.UpdateMode
                ? "UpdatedStatus"
                : WordPluginSettings.Load().InsertionBackend == FormulaInsertionBackend.Ole
                    ? "OleInsertedStatus"
                    : "OmmlInsertedStatus";
            _statusSink.Post(
                WordStatusKind.Success,
                WordAddInText.Get(statusKey));
        }

        CompleteEditorSession(accepted.SessionGeneration, target);
        await _wordAdapter.ActivateForEditingAsync(cancellationToken);
    }

    public async Task LoadSelectedAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        WordFormulaEditTarget target = await _wordAdapter.LoadSelectedFormulaTargetAsync(cancellationToken);
        await SwitchEditorTargetAsync(target, cancellationToken);
    }

    public void CancelEditorFormula(long sessionGeneration)
    {
        if (!_editorSession.Complete(sessionGeneration))
        {
            return;
        }

        if (_editorTargetGeneration == sessionGeneration)
        {
            RestoreCurrentFormulaPreview();
            _editorTarget = null;
            _editorTargetGeneration = 0;
        }
    }

    public async Task DeleteSelectedAsync(CancellationToken cancellationToken)
    {
        using (_wordAdapter.BeginUndoRecord())
        {
            await _wordAdapter.DeleteSelectedFormulaAsync(cancellationToken);
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("DeletedStatus"));
    }

    public async Task RecognizeScreenshotAsync(CancellationToken cancellationToken)
    {
        _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OcrWaitingStatus"));
        try
        {
            string responseJson = await RunScreenshotOcrWithProgressAsync(cancellationToken);
            ProcessOcrResult(responseJson);
        }
        catch (InvalidOperationException exc) when (IsOcrAlreadyWaiting(exc.Message))
        {
            await _bridgeClient.CancelScreenshotOcrAsync(CancellationToken.None);
            await Task.Delay(300, CancellationToken.None);
            try
            {
                string responseJson = await RunScreenshotOcrWithProgressAsync(cancellationToken);
                ProcessOcrResult(responseJson);
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

    private void ProcessOcrResult(string responseJson)
    {
        string latex = BridgeRecognitionParser.ParseScreenshotOcrResponse(responseJson);
        if (string.IsNullOrWhiteSpace(latex))
        {
            return;
        }

        _statusSink.SetCurrentFormula(latex, updateMode: false);
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

        FormulaMetadata numbered = WithNumbering(
            selected,
            NumberingMode.Automatic,
            string.Empty);
        await UpdateRenderedFormulaAsync(numbered, cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("AutoNumberedStatus"));
    }

    public async Task RenumberAllAsync(CancellationToken cancellationToken)
    {
        WordRenumberResult result;
        using (_wordAdapter.BeginUndoRecord())
        {
            result = await _wordAdapter.RenumberAutomaticFormulasAsync(cancellationToken);
        }

        bool foundNoNumberedFormula = result.RenumberedCount == 0 && result.SkippedCount == 0;
        string message = BuildRenumberStatusMessage(result, foundNoNumberedFormula);
        _statusSink.Post(foundNoNumberedFormula ? WordStatusKind.Info : WordStatusKind.Success, message);
    }

    private static string BuildRenumberStatusMessage(WordRenumberResult result, bool foundNoNumberedFormula)
    {
        if (foundNoNumberedFormula)
        {
            return WordAddInText.Get("NoNumberedStatus");
        }

        string messageKey = result.SkippedCount > 0 ? "RenumberedWithSkippedStatus" : "RenumberedStatus";
        return WordAddInText.Get(messageKey)
            .Replace("{count}", result.RenumberedCount.ToString(CultureInfo.InvariantCulture))
            .Replace("{metadataSkipped}", result.SkippedMetadataCount.ToString(CultureInfo.InvariantCulture))
            .Replace("{numberingSkipped}", result.SkippedNumberingCount.ToString(CultureInfo.InvariantCulture));
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

    private Task UpdateRenderedFormulaAsync(FormulaMetadata metadata, CancellationToken cancellationToken)
    {
        return UpdateRenderedFormulaAsync(metadata, target: null, cancellationToken);
    }

    private async Task UpdateRenderedFormulaAsync(
        FormulaMetadata metadata,
        WordFormulaEditTarget? target,
        CancellationToken cancellationToken,
        bool reportStatus = true)
    {
        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
            metadata,
            includeEquationOoxml: true,
            cancellationToken,
            reportProgress: reportStatus);
        using (_wordAdapter.BeginUndoRecord())
        {
            await UpdatePreparedFormulaAsync(prepared, target, cancellationToken, reportStatus);
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
        FormulaInsertionBackend backend = backendOverride
            ?? (includeEquationOoxml
                ? GetBackend(metadata.RenderEngine)
                : settings.InsertionBackend);
        string renderedLatex = metadata.Latex;
        if (backend == FormulaInsertionBackend.Ole)
        {
            if (reportProgress)
            {
                _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OleInsertingStatus"));
            }

            FormulaMetadata oleMetadata = WithRenderEngine(metadata, RenderEngineKind.MathJaxSvg);
            OlePresentationResult presentation = await RenderOlePresentationAsync(oleMetadata, renderedLatex, cancellationToken);
            return new PreparedWordFormula(oleMetadata, IsDisplay(oleMetadata), presentation, null, null, null);
        }

        if (reportProgress)
        {
            _statusSink.Post(WordStatusKind.Info, WordAddInText.Get("OmmlInsertingStatus"));
        }
        string mathMl = await _mathJaxRenderer.ConvertToMathMlAsync(renderedLatex, metadata.DisplayMode, cancellationToken);
        string omml = _ommlConverter.Convert(mathMl);
        string ooxml = WordOmmlDocumentBuilder.BuildFlatOpcDocument(omml, metadata, IsDisplay(metadata), settings.NumberPlacement);
        string? equationOoxml = includeEquationOoxml ? WordOmmlDocumentBuilder.BuildFlatOpcInlineEquationDocument(omml, metadata) : null;
        string? equationContentOoxml = includeEquationOoxml ? WordOmmlDocumentBuilder.BuildFlatOpcEquationContentDocument(omml) : null;
        return new PreparedWordFormula(metadata, IsDisplay(metadata), null, ooxml, equationOoxml, equationContentOoxml);
    }

    private async Task InsertPreparedFormulaAsync(
        PreparedWordFormula prepared,
        CancellationToken cancellationToken,
        bool reportStatus = true)
    {
        if (prepared.OlePresentation != null)
        {
            await _wordAdapter.InsertOleFormulaObjectAsync(prepared.Metadata, prepared.OlePresentation, prepared.Display, cancellationToken);
            if (reportStatus)
            {
                _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("OleInsertedStatus"));
            }
            return;
        }

        await _wordAdapter.InsertManagedEquationAsync(
            prepared.Ooxml!,
            prepared.Metadata,
            prepared.Display,
            cancellationToken);
        if (reportStatus)
        {
            _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("OmmlInsertedStatus"));
        }
    }

    private Task UpdatePreparedFormulaAsync(
        PreparedWordFormula prepared,
        CancellationToken cancellationToken,
        bool reportStatus = true)
    {
        return UpdatePreparedFormulaAsync(prepared, target: null, cancellationToken, reportStatus);
    }

    private async Task UpdatePreparedFormulaAsync(
        PreparedWordFormula prepared,
        WordFormulaEditTarget? target,
        CancellationToken cancellationToken,
        bool reportStatus = true)
    {
        if (prepared.OlePresentation != null)
        {
            if (target != null)
            {
                await _wordAdapter.UpdateOleFormulaObjectAsync(target, prepared.Metadata, prepared.OlePresentation, prepared.Display, cancellationToken);
            }
            else
            {
                await _wordAdapter.UpdateOleFormulaObjectAsync(prepared.Metadata.Identity.EquationId, prepared.Metadata, prepared.OlePresentation, prepared.Display, cancellationToken);
            }
            if (reportStatus)
            {
                _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("UpdatedStatus"));
            }
            return;
        }

        if (target != null)
        {
            await _wordAdapter.UpdateFormulaAsync(
                target,
                prepared.Ooxml!,
                prepared.EquationOoxml!,
                prepared.EquationContentOoxml!,
                prepared.Metadata,
                prepared.Display,
                cancellationToken);
        }
        else
        {
            await _wordAdapter.UpdateFormulaAsync(
                prepared.Metadata.Identity.EquationId,
                prepared.Ooxml!,
                prepared.EquationOoxml!,
                prepared.EquationContentOoxml!,
                prepared.Metadata,
                prepared.Display,
                cancellationToken);
        }
        if (reportStatus)
        {
            _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("UpdatedStatus"));
        }
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
        if (_editorTarget != null)
        {
            _optionsProvider.ResetFormulaDraft();
        }
        _editorTarget = null;
        _pendingEditorInsertOptions = options;
        FormulaMetadata draft = CreateEditorDraftFromOptions(options);
        _editorTargetGeneration = await _editorSession.OpenForInsertAsync(draft, cancellationToken);
        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("EditorReadyStatus"));
    }

    private WordFormulaEditTarget GetEditorTarget(FormulaEditorAcceptedEventArgs accepted)
    {
        if (_editorTarget == null
            || _editorTargetGeneration != accepted.SessionGeneration
            || !string.Equals(
                _editorTarget.Metadata.Identity.DocumentId,
                accepted.InitialFormula.Identity.DocumentId,
                StringComparison.Ordinal)
            || !string.Equals(
                _editorTarget.Metadata.Identity.EquationId,
                accepted.InitialFormula.Identity.EquationId,
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        return _editorTarget;
    }

    private async Task SwitchEditorTargetAsync(
        WordFormulaEditTarget target,
        CancellationToken cancellationToken)
    {
        if (target == null)
        {
            throw new ArgumentNullException(nameof(target));
        }

        if (!_wordAdapter.IsFormulaEditTargetValid(target))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        if (_editorTarget != null)
        {
            _optionsProvider.ResetFormulaDraft();
        }

        _editorTarget = target;
        _editorTargetGeneration = 0;
        _pendingEditorInsertOptions = null;
        try
        {
            _optionsProvider.ApplyFormulaMetadata(target.Metadata, updateMode: true);
            long generation = await _editorSession.OpenForEditAsync(target.Metadata, cancellationToken).ConfigureAwait(true);
            if (!ReferenceEquals(_editorTarget, target)
                || !_editorSession.IsCurrent(generation, target.Metadata.Identity))
            {
                return;
            }

            _editorTargetGeneration = generation;
        }
        catch
        {
            if (!ReferenceEquals(_editorTarget, target))
            {
                return;
            }

            _optionsProvider.ResetFormulaDraft();
            _editorTarget = null;
            _editorTargetGeneration = 0;
            throw;
        }

        _statusSink.Post(WordStatusKind.Success, WordAddInText.Get("LoadedStatus"));
    }

    private void CompleteEditorSession(long sessionGeneration, WordFormulaEditTarget? target)
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
    }

    private void RestoreCurrentFormulaPreview()
    {
        if (_editorTarget != null)
        {
            _optionsProvider.ResetFormulaDraft();
        }
    }

    private async Task InsertAndRenumberIfNeededAsync(
        FormulaMetadata metadata,
        CancellationToken cancellationToken,
        bool reportStatus = true)
    {
        if (metadata.NumberingMode == NumberingMode.Automatic)
        {
            metadata = WithNumbering(
                metadata,
                NumberingMode.Automatic,
                string.Empty);
        }

        await _wordAdapter.ValidateCurrentInsertionTargetAsync(cancellationToken);
        PreparedWordFormula prepared = await PrepareRenderedFormulaAsync(
            metadata,
            includeEquationOoxml: false,
            cancellationToken,
            reportProgress: reportStatus);
        using (_wordAdapter.BeginUndoRecord())
        {
            await InsertPreparedFormulaAsync(prepared, cancellationToken, reportStatus);
        }
    }

    private FormulaMetadata CreateMetadataFromDraft(
        FormulaIdentity? identity,
        string latex,
        FormulaMetadata? previous)
    {
        if (previous != null)
        {
            string normalizedLatex = NormalizeFormulaLatex(latex);
            return new FormulaMetadata(
                identity ?? previous.Identity,
                normalizedLatex,
                previous.DisplayMode,
                previous.NumberingMode,
                previous.NumberText,
                previous.RenderEngine,
                previous.SchemaVersion,
                previous.FontScale);
        }

        WordFormulaOptions options = _optionsProvider.GetFormulaOptions();
        return CreateMetadataFromOptions(identity, latex, previous, options);
    }

    private FormulaMetadata CreateMetadataFromOptions(
        FormulaIdentity? identity,
        string latex,
        FormulaMetadata? previous,
        WordFormulaOptions options)
    {
        string normalizedLatex = NormalizeFormulaLatex(latex);
        NumberingMode numberingMode = options.NumberingMode;
        string numberText = string.Empty;
        if (numberingMode == NumberingMode.Automatic)
        {
            numberText = string.Empty;
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
        if (previous == null)
        {
            normalizedLatex = ApplyDefaultSourceFormatting(
                normalizedLatex,
                settings.FormulaFontStyle,
                settings.FormulaColor);
        }
        FormulaMetadata metadata = new FormulaMetadata(
            identity ?? new FormulaIdentity(_wordAdapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
            normalizedLatex,
            displayMode,
            numberingMode,
            numberText,
            RenderEngineKind.Omml,
            schemaVersion: FormulaMetadata.CurrentSchemaVersion,
            previous?.FontScale ?? settings.FormulaFontScale);
        return metadata;
    }

    private FormulaMetadata CreateEditorDraftFromOptions(WordFormulaOptions options)
    {
        NumberingMode numberingMode = options.NumberingMode;
        FormulaDisplayMode displayMode = options.Display || numberingMode != NumberingMode.None
            ? FormulaDisplayMode.Display
            : FormulaDisplayMode.Inline;
        WordPluginSettings settings = WordPluginSettings.Load();
        return new FormulaMetadata(
            new FormulaIdentity(_wordAdapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
            string.Empty,
            displayMode,
            numberingMode,
            options.ManualNumber.Trim(),
            RenderEngineKind.Omml,
            schemaVersion: FormulaMetadata.CurrentSchemaVersion,
            settings.FormulaFontScale);
    }

    private static string CreateDefaultLatex()
    {
        return "e^{i\\pi}+1=0";
    }

    private static string NormalizeFormulaLatex(string latex)
    {
        return string.IsNullOrWhiteSpace(latex)
            ? CreateDefaultLatex()
            : MathLiveLatexStyleNormalizer.NormalizeLatex(latex.Trim());
    }

    internal static string ApplyDefaultSourceFormatting(string latex, FormulaFontStyle fontStyle, string fontColor)
    {
        string formatted = MathLiveLatexStyleNormalizer.HasFontStyleFormatting(latex)
            ? latex
            : MathLiveLatexStyleNormalizer.ApplyRenderFontStyle(latex, fontStyle);
        if (MathLiveLatexStyleNormalizer.HasColorFormatting(formatted)
            || string.Equals(fontColor, "#000000", StringComparison.OrdinalIgnoreCase))
        {
            return formatted;
        }

        return "\\color{" + fontColor + "}{" + formatted + "}";
    }

    private static bool IsDisplay(FormulaMetadata metadata)
    {
        return metadata.DisplayMode == FormulaDisplayMode.Display;
    }

    private static bool IsSameRenderedFormula(FormulaMetadata left, FormulaMetadata right)
    {
        return string.Equals(left.Latex.Trim(), right.Latex.Trim(), StringComparison.Ordinal)
            && left.DisplayMode == right.DisplayMode
            && left.NumberingMode == right.NumberingMode
            && string.Equals(left.NumberText.Trim(), right.NumberText.Trim(), StringComparison.Ordinal)
            && Math.Abs(left.FontScale - right.FontScale) <= 0.001;
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
            metadata.FontScale);
    }

    private static FormulaInsertionBackend GetBackend(RenderEngineKind renderEngine)
    {
        return renderEngine == RenderEngineKind.MathJaxSvg
            ? FormulaInsertionBackend.Ole
            : FormulaInsertionBackend.WordOmml;
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
