using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private const int WdMainTextStory = 1;
    private const int WdNoProtection = -1;
    private const string ParsedFormulaSlot = "\u2060";

    public Task<IReadOnlyList<WordLatexParseCandidate>> FindLatexParseCandidatesAsync(
        bool all,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic scope = all ? CurrentDocument.Content.Duplicate : _wordApplication.Selection.Range.Duplicate;
        if (GetStoryType(scope) != WdMainTextStory || IsCollapsedRange(scope) || IsDocumentProtected())
        {
            return Task.FromResult<IReadOnlyList<WordLatexParseCandidate>>(Array.Empty<WordLatexParseCandidate>());
        }

        int scopeStart = GetRangeStart(scope);
        int scopeEnd = GetRangeEnd(scope);
        IReadOnlyList<RangeSpan> excluded = CollectUnsafeSpans(scopeStart, scopeEnd);
        var candidates = new List<WordLatexParseCandidate>();
        foreach (RangeSpan region in BuildParseRegions(scopeStart, scopeEnd))
        {
            foreach (RangeSpan safe in BuildSafeSpans(region.Start, region.End, excluded))
            {
                cancellationToken.ThrowIfCancellationRequested();
                string text = ReadRangeText(safe.Start, safe.End);
                foreach (LatexDelimiterMatch match in LatexDelimiterScanner.Scan(text))
                {
                    candidates.Add(new WordLatexParseCandidate(
                        safe.Start + match.Offset,
                        safe.Start + match.Offset + match.Length,
                        match.OriginalText,
                        match.Latex,
                        match.DisplayMode));
                }
            }
        }

        return Task.FromResult<IReadOnlyList<WordLatexParseCandidate>>(candidates);
    }

    private IReadOnlyList<RangeSpan> BuildParseRegions(int scopeStart, int scopeEnd)
    {
        var tableSpans = new List<RangeSpan>();
        var cellSpans = new List<RangeSpan>();
        dynamic tables = CurrentDocument.Tables;
        int tableCount = Convert.ToInt32(tables.Count);
        for (int tableIndex = 1; tableIndex <= tableCount; tableIndex++)
        {
            dynamic table = tables.Item(tableIndex);
            dynamic tableRange = table.Range;
            int tableStart = GetRangeStart(tableRange);
            int tableEnd = GetRangeEnd(tableRange);
            AddClippedSpan(tableSpans, scopeStart, scopeEnd, tableStart, tableEnd);

            dynamic cells = tableRange.Cells;
            int cellCount = Convert.ToInt32(cells.Count);
            for (int cellIndex = 1; cellIndex <= cellCount; cellIndex++)
            {
                dynamic cellRange = cells.Item(cellIndex).Range;
                int cellStart = GetRangeStart(cellRange);
                int cellEnd = GetCellContentEnd(cellRange);
                AddClippedSpan(cellSpans, scopeStart, scopeEnd, cellStart, cellEnd);
            }
        }

        var regions = new List<RangeSpan>();
        regions.AddRange(BuildSafeSpans(scopeStart, scopeEnd, MergeSpans(tableSpans)));
        regions.AddRange(cellSpans);
        return regions.OrderBy(span => span.Start).ThenBy(span => span.End).ToArray();
    }

    public Task ReplaceParsedOmmlFormulaAsync(
        WordLatexParseCandidate candidate,
        string ooxml,
        FormulaMetadata metadata,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(ooxml))
        {
            throw new ArgumentException("OMML OOXML is required.", nameof(ooxml));
        }

        ValidateParsedFormulaInput(candidate, metadata);
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic sourceRange = GetCurrentParsedSourceRange(candidate);
            double fontSizePoints = ReadPointSize(sourceRange.Font.Size);
            ParsedFormulaTarget target = PrepareParsedFormulaTarget(
                sourceRange,
                candidate,
                metadata.DisplayMode == FormulaDisplayMode.Display,
                useWholeDisplayParagraph: true);
            int insertionPoint = GetRangeStart(target.Range);
            try
            {
                target.Range.InsertXML(ooxml);
                object equationControl = FindInsertedFormulaControl(insertionPoint, metadata.Identity.EquationId);
                if (metadata.DisplayMode == FormulaDisplayMode.Inline)
                {
                    RemoveParsedInlineParagraphBreak(equationControl);
                }
                double naturalFontSize = ScaleFontSize(fontSizePoints, metadata.FontScale);
                ApplyManagedEquationFontSize(equationControl, naturalFontSize);
                ShowContentControlChrome((dynamic)equationControl);
                WordFormulaMetadataStore.SaveOmmlNaturalFontSize(
                    CurrentDocument,
                    metadata.Identity.EquationId,
                    naturalFontSize);
                ApplyManagedEquationStyle(equationControl, metadata);
                if (metadata.DisplayMode == FormulaDisplayMode.Inline)
                {
                    ResetManagedEquationBaseline(equationControl);
                }
                else if (metadata.NumberingMode != NumberingMode.None)
                {
                    ApplyNumberedFormulaParagraphLayout(((dynamic)equationControl).Range);
                    if (metadata.NumberingMode == NumberingMode.Automatic)
                    {
                        InsertManagedEquationNumber(
                            equationControl,
                            metadata,
                            BuildEquationNumberStateAtPosition(insertionPoint, WordPluginSettings.Load()));
                    }
                }

                SaveFormulaMetadata(metadata);
            }
            catch
            {
                RestoreParsedFormulaText(candidate, metadata, target);
                throw;
            }
        });
        return Task.CompletedTask;
    }

    public Task ReplaceParsedOleFormulaAsync(
        WordLatexParseCandidate candidate,
        FormulaMetadata metadata,
        OlePresentationResult presentation,
        CancellationToken cancellationToken)
    {
        if (presentation == null)
        {
            throw new ArgumentNullException(nameof(presentation));
        }

        ValidateParsedFormulaInput(candidate, metadata);
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic sourceRange = GetCurrentParsedSourceRange(candidate);
            ParsedFormulaTarget target = PrepareParsedFormulaTarget(
                sourceRange,
                candidate,
                metadata.DisplayMode == FormulaDisplayMode.Display,
                useWholeDisplayParagraph: false);
            try
            {
                dynamic inlineShape = metadata.NumberingMode == NumberingMode.None
                    ? InsertPlainOleInlineShape(target.Range, metadata, presentation, metadata.DisplayMode == FormulaDisplayMode.Display)
                    : InsertNumberedOleInlineShape(target.Range, metadata, presentation);
                _ = inlineShape;
                SaveFormulaMetadata(metadata);
            }
            catch
            {
                RestoreParsedFormulaText(candidate, metadata, target);
                throw;
            }
        });
        return Task.CompletedTask;
    }

    private dynamic GetCurrentParsedSourceRange(WordLatexParseCandidate candidate)
    {
        dynamic range = CreateDocumentRange(candidate.Start, candidate.End);
        string current = Convert.ToString(range.Text) ?? string.Empty;
        if (!string.Equals(current, candidate.OriginalText, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(WordAddInText.Get("ParseSourceChangedError"));
        }

        if (RangeIsUnsafe(range, candidate.Start, candidate.End))
        {
            throw new InvalidOperationException("The formula source range is no longer safe to replace.");
        }

        return range;
    }

    private ParsedFormulaTarget PrepareParsedFormulaTarget(
        dynamic sourceRange,
        WordLatexParseCandidate candidate,
        bool display,
        bool useWholeDisplayParagraph)
    {
        string originalOoxml = ReadWordOpenXml(sourceRange);
        if (!display)
        {
            sourceRange.Text = ParsedFormulaSlot;
            dynamic inlineSlot = CreateDocumentRange(candidate.Start, candidate.Start + ParsedFormulaSlot.Length);
            if (!useWholeDisplayParagraph)
            {
                inlineSlot.Delete();
                inlineSlot = CreateDocumentRange(candidate.Start, candidate.Start);
            }
            return new ParsedFormulaTarget(
                inlineSlot,
                originalOoxml,
                hasLeadingParagraphBreak: false,
                hasTrailingParagraphBreak: false);
        }

        dynamic firstParagraph = sourceRange.Paragraphs.Item(1).Range;
        dynamic lastParagraph = sourceRange.Paragraphs.Item(sourceRange.Paragraphs.Count).Range;
        string leadingText = ReadRangeText(GetRangeStart(firstParagraph), candidate.Start);
        string trailingText = ReadRangeText(candidate.End, GetParagraphContentEnd(lastParagraph));
        string prefix = HasVisibleText(leadingText) ? "\r" : string.Empty;
        string suffix = HasVisibleText(trailingText) ? "\r" : string.Empty;
        sourceRange.Text = prefix + ParsedFormulaSlot + suffix;
        int slotStart = candidate.Start + prefix.Length;
        dynamic slot = CreateDocumentRange(slotStart, slotStart + ParsedFormulaSlot.Length);
        dynamic paragraph = slot.Paragraphs.Item(1).Range;
        if (useWholeDisplayParagraph)
        {
            return new ParsedFormulaTarget(paragraph, originalOoxml, prefix.Length > 0, suffix.Length > 0);
        }

        slot.Delete();
        return new ParsedFormulaTarget(
            CreateDocumentRange(slotStart, slotStart),
            originalOoxml,
            prefix.Length > 0,
            suffix.Length > 0);
    }

    private void RestoreParsedFormulaText(
        WordLatexParseCandidate candidate,
        FormulaMetadata metadata,
        ParsedFormulaTarget target)
    {
        try
        {
            dynamic restore = CreateParsedRestoreRange(candidate, metadata, target);
            if (!string.IsNullOrWhiteSpace(target.OriginalOoxml))
            {
                restore.InsertXML(target.OriginalOoxml);
            }
            else
            {
                restore.Text = candidate.OriginalText;
            }
        }
        catch
        {
            try
            {
                dynamic restore = CreateParsedRestoreRange(candidate, metadata, target);
                restore.Text = candidate.OriginalText;
            }
            catch
            {
            }
        }
    }

    private dynamic CreateParsedRestoreRange(
        WordLatexParseCandidate candidate,
        FormulaMetadata metadata,
        ParsedFormulaTarget target)
    {
        int start = ClampDocumentPosition(candidate.Start);
        if (candidate.DisplayMode == FormulaDisplayMode.Inline)
        {
            int end = start;
            object? control = TryGetEquationControlById(metadata.Identity.EquationId);
            if (control != null)
            {
                end = GetRangeEnd(((dynamic)control).Range);
            }
            else
            {
                object? inlineShape = TryFindOleInlineShapeById(metadata.Identity.EquationId);
                if (inlineShape != null)
                {
                    end = GetRangeEnd(((dynamic)inlineShape).Range);
                }
            }

            return CreateDocumentRange(start, Math.Max(start, end));
        }

        int formulaPosition = start + (target.HasLeadingParagraphBreak ? 1 : 0);
        dynamic formulaParagraph = CreateDocumentRange(formulaPosition, formulaPosition).Paragraphs.Item(1).Range;
        int endPosition = target.HasTrailingParagraphBreak
            ? GetRangeEnd(formulaParagraph)
            : GetParagraphContentEnd(formulaParagraph);
        return CreateDocumentRange(start, Math.Max(start, endPosition));
    }

    private void RemoveParsedInlineParagraphBreak(object equationControl)
    {
        dynamic control = equationControl;
        int position = GetRangeEnd(control.Range);
        int documentEnd = GetRangeEnd(CurrentDocument.Content);
        if (position >= documentEnd)
        {
            return;
        }

        for (int cursor = position; cursor < Math.Min(documentEnd, position + 3); cursor++)
        {
            dynamic following = CreateDocumentRange(cursor, Math.Min(documentEnd, cursor + 1));
            string text = Convert.ToString(following.Text) ?? string.Empty;
            if (text.Length == 0)
            {
                continue;
            }

            if (string.Equals(text, "\r", StringComparison.Ordinal))
            {
                following.Delete();
            }
            return;
        }
    }

    private static string ReadWordOpenXml(dynamic range)
    {
        try
        {
            return Convert.ToString(range.WordOpenXML) ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }

    private bool RangeIsUnsafe(dynamic range, int start, int end)
    {
        if (IsDocumentProtected() || GetStoryType(range) != WdMainTextStory)
        {
            return true;
        }

        return CollectUnsafeSpans(start, end).Any(span => RangesOverlap(start, end, span.Start, span.End));
    }

    private IReadOnlyList<RangeSpan> CollectUnsafeSpans(int scopeStart, int scopeEnd)
    {
        var spans = new List<RangeSpan>();
        bool complete = true;
        complete &= AddObjectRanges(spans, scopeStart, scopeEnd, "content controls", () => CurrentDocument.ContentControls, item => item.Range);
        complete &= AddObjectRanges(spans, scopeStart, scopeEnd, "native equations", () => CurrentDocument.OMaths, item => item.Range);
        complete &= AddObjectRanges(spans, scopeStart, scopeEnd, "inline shapes", () => CurrentDocument.InlineShapes, item => item.Range);
        complete &= AddObjectRanges(spans, scopeStart, scopeEnd, "hyperlinks", () => CurrentDocument.Hyperlinks, item => item.Range);
        complete &= AddObjectRanges(spans, scopeStart, scopeEnd, "comments", () => CurrentDocument.Comments, item => item.Scope);
        complete &= AddObjectRanges(spans, scopeStart, scopeEnd, "revisions", () => CurrentDocument.Revisions, item => item.Range);
        complete &= AddFieldRanges(spans, scopeStart, scopeEnd);
        complete &= AddCodeStyleRanges(spans, scopeStart, scopeEnd);
        if (!complete)
        {
            return new[] { new RangeSpan(scopeStart, scopeEnd) };
        }

        return MergeSpans(spans);
    }

    private static bool AddObjectRanges(
        ICollection<RangeSpan> spans,
        int scopeStart,
        int scopeEnd,
        string collectionName,
        Func<dynamic> collectionFactory,
        Func<dynamic, dynamic> rangeSelector)
    {
        try
        {
            dynamic collection = collectionFactory();
            int count = Convert.ToInt32(collection.Count);
            for (int index = 1; index <= count; index++)
            {
                dynamic range = rangeSelector(collection.Item(index));
                AddClippedSpan(
                    spans,
                    scopeStart,
                    scopeEnd,
                    GetRangeStart(range),
                    GetRangeEnd(range));
            }
            return true;
        }
        catch (Exception exception)
        {
            System.Diagnostics.Trace.TraceWarning(
                "Formula parsing could not inspect {0}: {1}: {2}",
                collectionName,
                exception.GetType().Name,
                exception.Message);
            return false;
        }
    }

    private bool AddFieldRanges(ICollection<RangeSpan> spans, int scopeStart, int scopeEnd)
    {
        try
        {
            dynamic fields = CurrentDocument.Fields;
            int count = Convert.ToInt32(fields.Count);
            for (int index = 1; index <= count; index++)
            {
                dynamic field = fields.Item(index);
                int start = Math.Min(GetRangeStart(field.Code), GetRangeStart(field.Result));
                int end = Math.Max(GetRangeEnd(field.Code), GetRangeEnd(field.Result));
                AddClippedSpan(spans, scopeStart, scopeEnd, Math.Max(0, start - 1), end + 1);
            }
            return true;
        }
        catch
        {
            return false;
        }
    }

    private bool AddCodeStyleRanges(ICollection<RangeSpan> spans, int scopeStart, int scopeEnd)
    {
        try
        {
            dynamic scope = CreateDocumentRange(scopeStart, scopeEnd);
            dynamic paragraphs = scope.Paragraphs;
            int count = Convert.ToInt32(paragraphs.Count);
            for (int index = 1; index <= count; index++)
            {
                dynamic range = paragraphs.Item(index).Range;
                if (IsCodeStyle(range))
                {
                    AddClippedSpan(spans, scopeStart, scopeEnd, GetRangeStart(range), GetRangeEnd(range));
                }
            }
            return true;
        }
        catch
        {
            return false;
        }
    }

    private static bool IsCodeStyle(dynamic range)
    {
        string name;
        try
        {
            dynamic style = range.Style;
            try
            {
                name = Convert.ToString(style.NameLocal) ?? string.Empty;
            }
            catch
            {
                name = Convert.ToString(style) ?? string.Empty;
            }
        }
        catch
        {
            return false;
        }

        string normalized = name.Trim().ToLowerInvariant();
        return normalized == "code"
            || normalized == "html code"
            || normalized == "html preformatted"
            || normalized == "preformatted"
            || normalized == "代码"
            || normalized == "html 代码"
            || normalized == "html 预设格式";
    }

    private bool IsDocumentProtected()
    {
        try
        {
            return Convert.ToInt32(CurrentDocument.ProtectionType) != WdNoProtection;
        }
        catch
        {
            return true;
        }
    }

    private static int GetStoryType(dynamic range)
    {
        try
        {
            return Convert.ToInt32(range.StoryType);
        }
        catch
        {
            return 0;
        }
    }

    private string ReadRangeText(int start, int end)
    {
        if (end <= start)
        {
            return string.Empty;
        }

        return Convert.ToString(CreateDocumentRange(start, end).Text) ?? string.Empty;
    }

    private static int GetParagraphContentEnd(dynamic paragraphRange)
    {
        int start = GetRangeStart(paragraphRange);
        int end = GetRangeEnd(paragraphRange);
        string text = Convert.ToString(paragraphRange.Text) ?? string.Empty;
        int trailingMarkers = text.EndsWith("\r\a", StringComparison.Ordinal) ? 2 : text.EndsWith("\r", StringComparison.Ordinal) ? 1 : 0;
        return Math.Max(start, end - trailingMarkers);
    }

    private static int GetCellContentEnd(dynamic cellRange)
    {
        int start = GetRangeStart(cellRange);
        int end = GetRangeEnd(cellRange);
        string text = Convert.ToString(cellRange.Text) ?? string.Empty;
        int trailingMarkers = text.EndsWith("\r\a", StringComparison.Ordinal) ? 1 : 0;
        return Math.Max(start, end - trailingMarkers);
    }

    private static bool HasVisibleText(string text)
    {
        return text.Any(character => !char.IsWhiteSpace(character) && character != '\a');
    }

    private static void AddClippedSpan(
        ICollection<RangeSpan> spans,
        int scopeStart,
        int scopeEnd,
        int start,
        int end)
    {
        int clippedStart = Math.Max(scopeStart, start);
        int clippedEnd = Math.Min(scopeEnd, end);
        if (clippedEnd > clippedStart)
        {
            spans.Add(new RangeSpan(clippedStart, clippedEnd));
        }
    }

    private static IReadOnlyList<RangeSpan> MergeSpans(IEnumerable<RangeSpan> spans)
    {
        RangeSpan[] ordered = spans.OrderBy(span => span.Start).ThenBy(span => span.End).ToArray();
        if (ordered.Length == 0)
        {
            return ordered;
        }

        var merged = new List<RangeSpan> { ordered[0] };
        for (int index = 1; index < ordered.Length; index++)
        {
            RangeSpan current = ordered[index];
            RangeSpan previous = merged[merged.Count - 1];
            if (current.Start <= previous.End)
            {
                merged[merged.Count - 1] = new RangeSpan(previous.Start, Math.Max(previous.End, current.End));
            }
            else
            {
                merged.Add(current);
            }
        }

        return merged;
    }

    private static IReadOnlyList<RangeSpan> BuildSafeSpans(
        int scopeStart,
        int scopeEnd,
        IReadOnlyList<RangeSpan> excluded)
    {
        var safe = new List<RangeSpan>();
        int cursor = scopeStart;
        foreach (RangeSpan span in excluded)
        {
            if (span.Start > cursor)
            {
                safe.Add(new RangeSpan(cursor, Math.Min(span.Start, scopeEnd)));
            }

            cursor = Math.Max(cursor, span.End);
            if (cursor >= scopeEnd)
            {
                return safe;
            }
        }

        if (cursor < scopeEnd)
        {
            safe.Add(new RangeSpan(cursor, scopeEnd));
        }

        return safe;
    }

    private static void ValidateParsedFormulaInput(WordLatexParseCandidate candidate, FormulaMetadata metadata)
    {
        if (candidate == null)
        {
            throw new ArgumentNullException(nameof(candidate));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        if (candidate.DisplayMode != metadata.DisplayMode)
        {
            throw new ArgumentException("Parsed formula display mode does not match its metadata.", nameof(metadata));
        }
    }

    private readonly struct RangeSpan
    {
        public RangeSpan(int start, int end)
        {
            Start = start;
            End = end;
        }

        public int Start { get; }

        public int End { get; }
    }

    private sealed class ParsedFormulaTarget
    {
        public ParsedFormulaTarget(
            object range,
            string originalOoxml,
            bool hasLeadingParagraphBreak,
            bool hasTrailingParagraphBreak)
        {
            Range = range;
            OriginalOoxml = originalOoxml;
            HasLeadingParagraphBreak = hasLeadingParagraphBreak;
            HasTrailingParagraphBreak = hasTrailingParagraphBreak;
        }

        public dynamic Range { get; }

        public string OriginalOoxml { get; }

        public bool HasLeadingParagraphBreak { get; }

        public bool HasTrailingParagraphBreak { get; }
    }
}
