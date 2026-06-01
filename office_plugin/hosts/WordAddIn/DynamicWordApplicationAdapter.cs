using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class DynamicWordApplicationAdapter : IWordApplicationAdapter
{
    private const int WdCollapseEnd = 0;
    private const int WdCharacter = 1;
    private const int WdMove = 0;
    private const int WdAutoFitFixed = 0;
    private const int WdAlignRowCenter = 1;
    private const int WdCellAlignVerticalCenter = 1;
    private const int WdPreferredWidthPercent = 2;
    private const int WdAlignParagraphCenter = 1;
    private const int WdContentControlRichText = 0;
    private const string OleFormulaProgId = "LaTeXSnipper.Formula";

    private readonly dynamic _wordApplication;

    private sealed class NumberedFormulaEntry
    {
        public NumberedFormulaEntry(string equationId, object numberControl, FormulaMetadata metadata, int start)
        {
            EquationId = equationId;
            NumberControl = numberControl;
            Metadata = metadata;
            Start = start;
        }

        public string EquationId { get; }

        public object NumberControl { get; }

        public FormulaMetadata Metadata { get; }

        public int Start { get; }
    }

    public DynamicWordApplicationAdapter(object wordApplication)
    {
        _wordApplication = wordApplication ?? throw new ArgumentNullException(nameof(wordApplication));
    }

    public Task ValidateCurrentInsertionTargetAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        ValidateInsertionTarget(range);
        return Task.CompletedTask;
    }

    public Task InsertManagedEquationAsync(string ooxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken)
    {
        ValidateManagedEquationInput(ooxml, metadata);
        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic selection = _wordApplication.Selection;
            dynamic range = ResolveInsertionTargetRange(selection);
            ValidateInsertionTarget(range);
            range.InsertXML(ooxml);
            WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
            MoveSelectionAfterInsertedFormula(metadata, display);
        });

        return Task.CompletedTask;
    }

    public Task InsertOleFormulaObjectAsync(FormulaMetadata metadata, bool display, CancellationToken cancellationToken)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        cancellationToken.ThrowIfCancellationRequested();
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            dynamic selection = _wordApplication.Selection;
            dynamic range = ResolveInsertionTargetRange(selection);
            ValidateInsertionTarget(range);
            OleFormulaPendingPayloadStore.SavePendingPayload(metadata);
            dynamic inlineShape = _wordApplication.ActiveDocument.InlineShapes.AddOLEObject(
                OleFormulaProgId,
                Type.Missing,
                false,
                false,
                Type.Missing,
                Type.Missing,
                Type.Missing,
                range);
            WrapOleInlineShape(inlineShape, metadata);
            WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
            MoveSelectionAfterInsertedFormula(metadata, display);
        });

        return Task.CompletedTask;
    }

    private void WrapOleInlineShape(dynamic inlineShape, FormulaMetadata metadata)
    {
        dynamic control = _wordApplication.ActiveDocument.ContentControls.Add(WdContentControlRichText, inlineShape.Range);
        control.Tag = WordFormulaMetadataStore.BuildEquationTag(metadata.Identity.EquationId, metadata);
        control.Title = "LaTeXSnipper Equation";
        control.LockContentControl = true;
        control.LockContents = false;
    }

    public Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        SelectedWordFormula selected = FindSelectedFormula();
        return Task.FromResult(selected.Metadata);
    }

    public Task UpdateFormulaAsync(string equationId, string ooxml, string equationOoxml, FormulaMetadata metadata, bool display, CancellationToken cancellationToken)
    {
        ValidateManagedEquationInput(ooxml, metadata);
        ValidateManagedEquationInput(equationOoxml, metadata);
        cancellationToken.ThrowIfCancellationRequested();
        object control = FindFormulaControlById(equationId);
        ExecuteWithScreenUpdatingSuspended(() => ReplaceFormulaContent(control, ooxml, equationOoxml, metadata));
        return Task.CompletedTask;
    }

    public Task DeleteSelectedFormulaAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var selectedFormulas = new List<SelectedWordFormula>(FindSelectedFormulas());
        selectedFormulas.Sort((left, right) => GetFormulaStart(right).CompareTo(GetFormulaStart(left)));
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            foreach (SelectedWordFormula selected in selectedFormulas)
            {
                DeleteFormula(selected);
            }
        });

        return Task.CompletedTask;
    }

    public int GetNextAutomaticNumber()
    {
        return WordFormulaMetadataStore.GetAutoNumberCounter(_wordApplication.ActiveDocument);
    }

    public void SetNextAutomaticNumber(int number)
    {
        WordFormulaMetadataStore.SetAutoNumberCounter(_wordApplication.ActiveDocument, number);
    }

    public Task<int> RenumberAutomaticFormulasAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var entries = new List<NumberedFormulaEntry>(LoadNumberedFormulaEntries());
        entries.Sort((left, right) => left.Start.CompareTo(right.Start));
        int number = 0;
        ExecuteWithScreenUpdatingSuspended(() =>
        {
            foreach (NumberedFormulaEntry entry in entries)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (entry.Metadata.NumberingMode != NumberingMode.Automatic)
                {
                    continue;
                }

                number++;
                string numberText = "(" + number.ToString(System.Globalization.CultureInfo.InvariantCulture) + ")";
                ReplaceNumberControlText(entry.NumberControl, numberText);
                FormulaMetadata renumbered = new FormulaMetadata(
                    entry.Metadata.Identity,
                    entry.Metadata.Latex,
                    FormulaDisplayMode.Display,
                    NumberingMode.Automatic,
                    numberText,
                    entry.Metadata.RenderEngine,
                    entry.Metadata.SchemaVersion);
                WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, renumbered);
            }
        });

        SetNextAutomaticNumber(number + 1);
        return Task.FromResult(number);
    }

    private IReadOnlyList<NumberedFormulaEntry> LoadNumberedFormulaEntries()
    {
        var entries = new List<NumberedFormulaEntry>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int i = 1; i <= count; i++)
        {
            dynamic control = controls.Item(i);
            string tag = Convert.ToString(control.Tag) ?? string.Empty;
            string equationId = WordFormulaMetadataStore.EquationIdFromNumberTag(tag);
            if (string.IsNullOrWhiteSpace(equationId) || !seen.Add(equationId))
            {
                continue;
            }

            FormulaMetadata metadata = LoadFormulaMetadataById(equationId);
            entries.Add(new NumberedFormulaEntry(equationId, control, metadata, GetRangeStart(control.Range)));
        }

        return entries;
    }

    private FormulaMetadata LoadFormulaMetadataById(string equationId)
    {
        try
        {
            return WordFormulaMetadataStore.Load(_wordApplication.ActiveDocument, equationId);
        }
        catch
        {
            object equationControl = FindFormulaControlById(equationId);
            return LoadFormulaMetadata((dynamic)equationControl, equationId);
        }
    }

    private SelectedWordFormula FindSelectedFormula()
    {
        IReadOnlyList<SelectedWordFormula> formulas = FindSelectedFormulas();
        return formulas[0];
    }

    private IReadOnlyList<SelectedWordFormula> FindSelectedFormulas()
    {
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        var formulas = new List<SelectedWordFormula>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        AddSelectedFormula(formulas, seen, TryGetParentContentControl(range));
        AddSelectedFormulasFromRange(formulas, seen, range);
        AddSelectedFormulasFromNumberedTables(formulas, seen, range);
        AddSelectedFormulasOverlappingRange(formulas, seen, range);
        if (formulas.Count == 0)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
        }

        return formulas;
    }

    private void AddSelectedFormulasFromRange(ICollection<SelectedWordFormula> formulas, ISet<string> seen, dynamic range)
    {
        try
        {
            dynamic controls = range.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                AddSelectedFormula(formulas, seen, controls.Item(i));
            }
        }
        catch
        {
        }
    }

    private void AddSelectedFormulasFromNumberedTables(ICollection<SelectedWordFormula> formulas, ISet<string> seen, dynamic range)
    {
        try
        {
            dynamic tables = range.Tables;
            int tableCount = Convert.ToInt32(tables.Count);
            for (int i = 1; i <= tableCount; i++)
            {
                dynamic controls = tables.Item(i).Range.ContentControls;
                int controlCount = Convert.ToInt32(controls.Count);
                for (int j = 1; j <= controlCount; j++)
                {
                    AddSelectedFormula(formulas, seen, controls.Item(j));
                }
            }
        }
        catch
        {
        }
    }

    private void AddSelectedFormulasOverlappingRange(ICollection<SelectedWordFormula> formulas, ISet<string> seen, dynamic range)
    {
        int selectionStart = GetRangeStart(range);
        int selectionEnd = GetRangeEnd(range);
        if (selectionEnd <= selectionStart)
        {
            return;
        }

        try
        {
            dynamic controls = _wordApplication.ActiveDocument.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                dynamic controlRange = control.Range;
                if (RangesOverlap(GetRangeStart(controlRange), GetRangeEnd(controlRange), selectionStart, selectionEnd))
                {
                    AddSelectedFormula(formulas, seen, control);
                }
            }
        }
        catch
        {
        }
    }

    private void AddSelectedFormula(ICollection<SelectedWordFormula> formulas, ISet<string> seen, object? candidate)
    {
        if (candidate == null)
        {
            return;
        }

        dynamic control = candidate;
        string equationId = GetEquationId(control);
        if (string.IsNullOrWhiteSpace(equationId) || !seen.Add(equationId))
        {
            return;
        }

        object equationControl = IsEquationControl(control) ? candidate : FindFormulaControlById(equationId);
        FormulaMetadata metadata = LoadFormulaMetadata((dynamic)equationControl, equationId);
        formulas.Add(new SelectedWordFormula(equationControl, metadata));
    }

    private object FindFormulaControlById(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        dynamic controls = _wordApplication.ActiveDocument.ContentControls;
        int count = Convert.ToInt32(controls.Count);
        for (int i = 1; i <= count; i++)
        {
            dynamic control = controls.Item(i);
            if (GetEquationControlId(control) == equationId)
            {
                return control;
            }
        }

        throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaRequired"));
    }

    private void ReplaceFormulaContent(object contentControl, string ooxml, string equationOoxml, FormulaMetadata metadata)
    {
        dynamic control = contentControl;
        object? table = TryGetNumberedTable(control, metadata.Identity.EquationId);
        if (table != null)
        {
            ReplaceNumberedFormulaControl(control, equationOoxml);
        }
        else
        {
            dynamic range = ResolveReplacementRange(control, metadata);
            range.InsertXML(ooxml);
        }

        WordFormulaMetadataStore.Save(_wordApplication.ActiveDocument, metadata);
        if (metadata.NumberingMode != NumberingMode.None)
        {
            NormalizeNumberedFormula(metadata.Identity.EquationId);
        }
    }

    private void ReplaceFormulaContent(object contentControl, string ooxml, FormulaMetadata metadata)
    {
        ReplaceFormulaContent(contentControl, ooxml, ooxml, metadata);
    }

    private static void ReplaceNumberedFormulaControl(object contentControl, string equationOoxml)
    {
        dynamic control = contentControl;
        dynamic range = GetContainingParagraphRange(control);
        range.InsertXML(equationOoxml);
    }

    private static dynamic ResolveReplacementRange(dynamic control, FormulaMetadata metadata)
    {
        return metadata.DisplayMode == FormulaDisplayMode.Display
            ? GetContainingParagraphRange(control)
            : control.Range;
    }

    private object? TryGetNumberedTable(dynamic control, string equationId)
    {
        object? numberAnchoredTable = TryGetNumberedTableFromNumberControl(_wordApplication.ActiveDocument, equationId);
        if (numberAnchoredTable != null)
        {
            return numberAnchoredTable;
        }

        try
        {
            dynamic tables = control.Range.Tables;
            int tableCount = Convert.ToInt32(tables.Count);
            if (tableCount == 0)
            {
                return null;
            }

            dynamic table = tables.Item(1);
            if (TableContainsNumberControl(table, equationId) || TableContainsManagedControl(table, equationId))
            {
                return table;
            }
        }
        catch
        {
        }

        return null;
    }

    private static object? TryGetContainingTable(dynamic control)
    {
        try
        {
            dynamic tables = control.Range.Tables;
            int tableCount = Convert.ToInt32(tables.Count);
            return tableCount == 0 ? null : tables.Item(1);
        }
        catch
        {
            return null;
        }
    }

    private static object? TryGetNumberedTableFromNumberControl(dynamic document, string equationId)
    {
        try
        {
            dynamic controls = document.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                if (WordFormulaMetadataStore.EquationIdFromNumberTag(tag) != equationId)
                {
                    continue;
                }

                dynamic tables = control.Range.Tables;
                int tableCount = Convert.ToInt32(tables.Count);
                return tableCount == 0 ? null : tables.Item(1);
            }
        }
        catch
        {
        }

        return null;
    }

    private static bool TableContainsNumberControl(dynamic table, string equationId)
    {
        try
        {
            dynamic controls = table.Range.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                if (WordFormulaMetadataStore.EquationIdFromNumberTag(tag) == equationId)
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        return false;
    }

    private static bool TableContainsManagedControl(dynamic table, string equationId)
    {
        try
        {
            dynamic controls = table.Range.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (GetManagedEquationId(control) == equationId)
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        return false;
    }

    private void ValidateInsertionTarget(dynamic range)
    {
        if (RangeTouchesManagedFormula(range) || RangeIntersectsManagedFormula(range))
        {
            throw new InvalidOperationException(WordAddInText.Get("InsertInsideFormulaError"));
        }
    }

    private dynamic ResolveInsertionTargetRange(dynamic selection)
    {
        dynamic range = selection.Range;
        object? afterNumberedParagraph = TryResolveAfterEmptyParagraphFollowingNumberedTable(range);
        if (afterNumberedParagraph != null)
        {
            return afterNumberedParagraph;
        }

        object? numberedTable = TryGetNumberedTableFromRange(range);
        if (numberedTable == null)
        {
            return range;
        }

        throw new InvalidOperationException(WordAddInText.Get("InsertInsideFormulaError"));
    }

    private object? TryResolveAfterEmptyParagraphFollowingNumberedTable(dynamic range)
    {
        if (!IsCollapsedRange(range))
        {
            return null;
        }

        try
        {
            dynamic paragraphs = range.Paragraphs;
            if (Convert.ToInt32(paragraphs.Count) == 0)
            {
                return null;
            }

            dynamic paragraph = paragraphs.Item(1);
            if (!string.IsNullOrWhiteSpace(CleanRangeText(Convert.ToString(paragraph.Range.Text) ?? string.Empty)))
            {
                return null;
            }

            object? previousTable = TryGetNumberedTableFromPreviousParagraph(paragraph)
                ?? TryGetNumberedTableBeforeParagraph(paragraph);
            return previousTable == null ? null : CreateRangeAtDocumentPosition(GetRangeEnd(paragraph.Range));
        }
        catch
        {
            return null;
        }
    }

    private static object? TryGetNumberedTableFromPreviousParagraph(dynamic paragraph)
    {
        try
        {
            dynamic previous = paragraph.Previous();
            dynamic tables = previous.Range.Tables;
            int tableCount = Convert.ToInt32(tables.Count);
            for (int i = 1; i <= tableCount; i++)
            {
                dynamic table = tables.Item(i);
                if (TableContainsNumberControl(table))
                {
                    return table;
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private object? TryGetNumberedTableBeforeParagraph(dynamic paragraph)
    {
        try
        {
            int paragraphStart = GetRangeStart(paragraph.Range);
            dynamic tables = _wordApplication.ActiveDocument.Tables;
            int tableCount = Convert.ToInt32(tables.Count);
            object? closest = null;
            int closestEnd = -1;
            for (int i = 1; i <= tableCount; i++)
            {
                dynamic table = tables.Item(i);
                int tableEnd = GetRangeEnd(table.Range);
                if (tableEnd <= paragraphStart && tableEnd > closestEnd && TableContainsNumberControl(table))
                {
                    closest = table;
                    closestEnd = tableEnd;
                }
            }

            return closest;
        }
        catch
        {
            return null;
        }
    }

    private static object? TryGetNumberedTableFromRange(dynamic range)
    {
        try
        {
            dynamic tables = range.Tables;
            int tableCount = Convert.ToInt32(tables.Count);
            for (int i = 1; i <= tableCount; i++)
            {
                dynamic table = tables.Item(i);
                if (TableContainsNumberControl(table))
                {
                    return table;
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private static bool TableContainsNumberControl(dynamic table)
    {
        try
        {
            dynamic controls = table.Range.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(WordFormulaMetadataStore.EquationIdFromNumberTag(tag)))
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        return false;
    }

    private void MoveSelectionAfterInsertedFormula(FormulaMetadata metadata, bool display)
    {
        try
        {
            string equationId = metadata.Identity.EquationId;
            dynamic control = FindFormulaControlById(equationId);
            if (metadata.NumberingMode != NumberingMode.None)
            {
                object? table = TryGetNumberedTableFromNumberControl(_wordApplication.ActiveDocument, equationId)
                    ?? TryGetNumberedTable(control, equationId);
                if (table == null)
                {
                    MoveSelectionAfterDisplayParagraph(control, equationId);
                    return;
                }

                NormalizeNumberedFormula(equationId);
                MoveSelectionAfterTable(table, equationId);
                return;
            }

            if (!display)
            {
                MoveSelectionAfterInlineControl(control, equationId);
                return;
            }

            MoveSelectionAfterDisplayParagraph(control, equationId);
        }
        catch
        {
        }
    }

    private void MoveSelectionAfterInlineControl(dynamic control, string equationId)
    {
        object? metadataControl = TryGetMetadataControlById(_wordApplication.ActiveDocument, equationId);
        MoveSelectionAfterContentControl(metadataControl ?? control, equationId);
    }

    private void MoveSelectionAfterDisplayParagraph(dynamic control, string equationId)
    {
        dynamic paragraphRange = GetContainingParagraphRange(control);
        int insertionPoint = GetRangeEnd(paragraphRange);
        bool paragraphInserted = TryInsertParagraphAfter(paragraphRange);
        if (paragraphInserted &&
            (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1)))
        {
            return;
        }

        EnsureSelectionOutsideFormula(equationId);
    }

    private void MoveSelectionAfterTable(object table, string equationId)
    {
        dynamic numberedTable = table;
        try
        {
            numberedTable.Range.Select();
            _wordApplication.Selection.Collapse(WdCollapseEnd);
            _wordApplication.Selection.TypeParagraph();
            if (!RangeTouchesManagedFormula(_wordApplication.Selection.Range))
            {
                return;
            }
        }
        catch
        {
        }

        dynamic tableRange = numberedTable.Range;
        int insertionPoint = GetRangeEnd(tableRange);
        bool paragraphInserted = TryInsertParagraphAfter(tableRange);
        if (paragraphInserted && TryMoveSelectionOutsideFormula(insertionPoint + 1))
        {
            return;
        }

        numberedTable.Range.Select();
        _wordApplication.Selection.Collapse(WdCollapseEnd);
        if (!paragraphInserted)
        {
            _wordApplication.Selection.TypeParagraph();
        }

        EnsureSelectionOutsideFormula(equationId);
    }

    private void MoveSelectionAfterContentControl(object contentControl, string equationId)
    {
        dynamic control = contentControl;
        int insertionPoint = Convert.ToInt32(control.Range.End);
        if (TryMoveSelectionOutsideFormula(insertionPoint) || TryMoveSelectionOutsideFormula(insertionPoint + 1))
        {
            return;
        }

        dynamic target = CreateDocumentRange(insertionPoint, insertionPoint);
        target.Select();
        MoveSelectionRight();
        EnsureSelectionOutsideFormula(equationId);
    }

    private bool TryMoveSelectionOutsideFormula(int position)
    {
        try
        {
            int safePosition = ClampDocumentPosition(position);
            dynamic target = _wordApplication.ActiveDocument.Range(safePosition, safePosition);
            if (RangeTouchesManagedFormula(target))
            {
                return false;
            }

            try
            {
                _wordApplication.Selection.SetRange(safePosition, safePosition);
            }
            catch
            {
                target.Select();
            }

            return true;
        }
        catch
        {
            return false;
        }
    }

    private void EnsureSelectionOutsideFormula(string equationId)
    {
        try
        {
            for (int i = 0; i < 12; i++)
            {
                dynamic range = _wordApplication.Selection.Range;
                object? control = TryGetParentContentControl(range)
                    ?? TryGetFirstManagedContentControl(range)
                    ?? TryGetFirstManagedContentControlInNumberedTable(range);
                object? numberedTable = TryGetNumberedTableFromRange(range);
                if (control == null && numberedTable == null)
                {
                    return;
                }

                if (control != null && GetEquationId((dynamic)control) != equationId && numberedTable == null)
                {
                    return;
                }

                MoveSelectionRight();
            }
        }
        catch
        {
        }
    }

    private static bool TryInsertParagraphAfter(dynamic range)
    {
        try
        {
            range.InsertParagraphAfter();
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void MoveSelectionRight()
    {
        try
        {
            _wordApplication.Selection.MoveRight(WdCharacter, 1, WdMove);
        }
        catch
        {
        }
    }

    private static dynamic GetContainingParagraphRange(dynamic control)
    {
        dynamic paragraphs = control.Range.Paragraphs;
        return paragraphs.Item(1).Range;
    }

    private void NormalizeNumberedFormula(string equationId)
    {
        try
        {
            object? table = TryGetNumberedTableFromNumberControl(_wordApplication.ActiveDocument, equationId);
            if (table != null)
            {
                NormalizeNumberedTable(table);
            }
        }
        catch
        {
        }
    }

    private static void NormalizeNumberedTable(object table)
    {
        dynamic numberedTable = table;
        TryCom(() => numberedTable.AllowAutoFit = false);
        TryCom(() => numberedTable.AutoFitBehavior(WdAutoFitFixed));
        TryCom(() => numberedTable.PreferredWidthType = WdPreferredWidthPercent);
        TryCom(() => numberedTable.PreferredWidth = 100);
        TryCom(() => numberedTable.TopPadding = 0);
        TryCom(() => numberedTable.BottomPadding = 0);
        TryCom(() => numberedTable.LeftPadding = 0);
        TryCom(() => numberedTable.RightPadding = 0);
        TryCom(() => numberedTable.Spacing = 0);
        TryCom(() => numberedTable.Rows.Alignment = WdAlignRowCenter);
        TryCom(() => numberedTable.Rows.VerticalAlignment = WdCellAlignVerticalCenter);
        TryCom(() => numberedTable.Rows.Height = 0);
        TryCom(() => numberedTable.Rows.HeightRule = 0);
        TryCom(() => numberedTable.Borders.Enable = 0);
        NormalizeNumberedTableCell(numberedTable, column: 1, widthPercent: 15, alignment: 0);
        NormalizeNumberedTableCell(numberedTable, column: 2, widthPercent: 70, alignment: 1);
        NormalizeNumberedTableCell(numberedTable, column: 3, widthPercent: 15, alignment: 2);
    }

    private static void NormalizeNumberedTableCell(dynamic table, int column, int widthPercent, int alignment)
    {
        try
        {
            dynamic cell = table.Cell(1, column);
            TryCom(() => cell.VerticalAlignment = WdCellAlignVerticalCenter);
            TryCom(() => cell.PreferredWidthType = WdPreferredWidthPercent);
            TryCom(() => cell.PreferredWidth = widthPercent);
            TryCom(() => cell.Range.ParagraphFormat.Alignment = alignment);
            TryCom(() => cell.Range.ParagraphFormat.SpaceBefore = 0);
            TryCom(() => cell.Range.ParagraphFormat.SpaceAfter = 0);
            TryCom(() => cell.Range.ParagraphFormat.LineSpacingRule = 0);
            TryCom(() => cell.Range.ParagraphFormat.DisableLineHeightGrid = true);
        }
        catch
        {
        }
    }

    private void DeleteFormula(SelectedWordFormula selected)
    {
        dynamic control = selected.ContentControl;
        string equationId = selected.Metadata.Identity.EquationId;
        object? table = TryGetNumberedTable(control, equationId)
            ?? (selected.Metadata.NumberingMode == NumberingMode.None ? null : TryGetContainingTable(control));
        object? metadataControl = TryGetMetadataControlById(_wordApplication.ActiveDocument, equationId);
        WordFormulaMetadataStore.Delete(_wordApplication.ActiveDocument, equationId);
        if (table != null)
        {
            DeleteNumberedTableBlock(table);
            return;
        }

        control.Delete(true);
        if (metadataControl != null)
        {
            dynamic backup = metadataControl;
            backup.Delete(true);
        }
    }

    private void DeleteNumberedTableBlock(object table)
    {
        dynamic numberedTable = table;
        numberedTable.Delete();
    }

    private static int GetFormulaStart(SelectedWordFormula formula)
    {
        try
        {
            return Convert.ToInt32(((dynamic)formula.ContentControl).Range.Start);
        }
        catch
        {
            return 0;
        }
    }

    private FormulaMetadata LoadFormulaMetadata(dynamic control, string equationId)
    {
        try
        {
            return WordFormulaMetadataStore.Load(_wordApplication.ActiveDocument, equationId);
        }
        catch
        {
            return CreateRecoveredFormulaMetadata(control, equationId);
        }
    }

    private FormulaMetadata CreateRecoveredFormulaMetadata(dynamic control, string equationId)
    {
        object? table = TryGetNumberedTable(control, equationId);
        string numberText = ReadNumberText(equationId);
        NumberingMode numberingMode = string.IsNullOrWhiteSpace(numberText) ? NumberingMode.None : NumberingMode.Manual;
        FormulaDisplayMode displayMode = table != null || IsCenteredParagraph(control)
            ? FormulaDisplayMode.Display
            : FormulaDisplayMode.Inline;
        return new FormulaMetadata(
            new FormulaIdentity("active-document", equationId),
            ReadFormulaText(control),
            displayMode,
            numberingMode,
            numberText,
            RenderEngineKind.Omml,
            schemaVersion: 1);
    }

    private string ReadNumberText(string equationId)
    {
        object? control = TryGetNumberControlById(_wordApplication.ActiveDocument, equationId);
        return control == null ? string.Empty : CleanRangeText(((dynamic)control).Range.Text);
    }

    private static void ReplaceNumberControlText(object numberControl, string numberText)
    {
        dynamic control = numberControl;
        TryCom(() => control.Range.Text = numberText);
    }

    private static string ReadFormulaText(dynamic control)
    {
        try
        {
            return CleanRangeText(Convert.ToString(control.Range.Text) ?? string.Empty);
        }
        catch
        {
            return string.Empty;
        }
    }

    private static bool IsCenteredParagraph(dynamic control)
    {
        try
        {
            int alignment = Convert.ToInt32(control.Range.ParagraphFormat.Alignment);
            return alignment == WdAlignParagraphCenter;
        }
        catch
        {
            return false;
        }
    }

    private static string CleanRangeText(string value)
    {
        return value
            .Replace("\a", string.Empty)
            .Replace("\r", string.Empty)
            .Replace("\n", string.Empty)
            .Trim();
    }

    private static object? TryGetNumberControlById(dynamic document, string equationId)
    {
        return TryGetControlByTag(document, WordFormulaMetadataStore.BuildNumberTag(equationId));
    }

    private static object? TryGetMetadataControlById(dynamic document, string equationId)
    {
        return TryGetControlByTag(document, WordFormulaMetadataStore.BuildMetadataTag(equationId));
    }

    private static object? TryGetControlByTag(dynamic document, string expectedTag)
    {
        try
        {
            dynamic controls = document.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                string tag = Convert.ToString(control.Tag) ?? string.Empty;
                if (string.Equals(tag, expectedTag, StringComparison.Ordinal))
                {
                    return control;
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private dynamic CreateDocumentRange(int start, int end)
    {
        try
        {
            return _wordApplication.ActiveDocument.Range(start, end);
        }
        catch
        {
            return _wordApplication.ActiveDocument.Range(Math.Max(0, start - 1), Math.Max(0, end - 1));
        }
    }

    private dynamic CreateRangeAtDocumentPosition(int position)
    {
        int safePosition = ClampDocumentPosition(position);
        return _wordApplication.ActiveDocument.Range(safePosition, safePosition);
    }

    private int ClampDocumentPosition(int position)
    {
        try
        {
            int documentStart = Convert.ToInt32(_wordApplication.ActiveDocument.Content.Start);
            int documentEnd = Convert.ToInt32(_wordApplication.ActiveDocument.Content.End);
            return Math.Min(Math.Max(position, documentStart), documentEnd);
        }
        catch
        {
            return Math.Max(0, position);
        }
    }

    private static int GetRangeEnd(dynamic range)
    {
        return Convert.ToInt32(range.End);
    }

    private static int GetRangeStart(dynamic range)
    {
        return Convert.ToInt32(range.Start);
    }

    private static bool RangesOverlap(int leftStart, int leftEnd, int rightStart, int rightEnd)
    {
        return leftStart < rightEnd && leftEnd > rightStart;
    }

    private static bool IsCollapsedRange(dynamic range)
    {
        try
        {
            return Convert.ToInt32(range.Start) == Convert.ToInt32(range.End);
        }
        catch
        {
            return false;
        }
    }

    private static bool RangeTouchesManagedFormula(dynamic range)
    {
        return TryGetParentContentControl(range) != null
            || TryGetFirstManagedContentControl(range) != null
            || TryGetFirstManagedContentControlInNumberedTable(range) != null
            || TryGetNumberedTableFromRange(range) != null;
    }

    private bool RangeIntersectsManagedFormula(dynamic range)
    {
        int rangeStart = GetRangeStart(range);
        int rangeEnd = GetRangeEnd(range);
        try
        {
            dynamic controls = _wordApplication.ActiveDocument.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (!IsManagedControl(control))
                {
                    continue;
                }

                if (RangesIntersectOrContainPoint(rangeStart, rangeEnd, GetRangeStart(control.Range), GetRangeEnd(control.Range)))
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        try
        {
            dynamic tables = _wordApplication.ActiveDocument.Tables;
            int count = Convert.ToInt32(tables.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic table = tables.Item(i);
                if (!TableContainsNumberControl(table))
                {
                    continue;
                }

                if (RangesIntersectOrContainPoint(rangeStart, rangeEnd, GetRangeStart(table.Range), GetRangeEnd(table.Range)))
                {
                    return true;
                }
            }
        }
        catch
        {
        }

        return false;
    }

    private static bool RangesIntersectOrContainPoint(int rangeStart, int rangeEnd, int targetStart, int targetEnd)
    {
        if (rangeStart == rangeEnd)
        {
            return rangeStart >= targetStart && rangeStart < targetEnd;
        }

        return RangesOverlap(rangeStart, rangeEnd, targetStart, targetEnd);
    }

    private void ExecuteWithScreenUpdatingSuspended(Action action)
    {
        bool restore = false;
        bool original = true;
        try
        {
            original = Convert.ToBoolean(_wordApplication.ScreenUpdating);
            restore = true;
            _wordApplication.ScreenUpdating = false;
        }
        catch
        {
        }

        try
        {
            action();
        }
        finally
        {
            if (restore)
            {
                TryCom(() => _wordApplication.ScreenUpdating = original);
            }
        }
    }

    private static void TryCom(Action action)
    {
        try
        {
            action();
        }
        catch
        {
        }
    }

    private static object? TryGetParentContentControl(dynamic range)
    {
        try
        {
            dynamic control = range.ParentContentControl;
            return IsManagedControl(control) ? control : null;
        }
        catch
        {
            return null;
        }
    }

    private static object? TryGetFirstManagedContentControl(dynamic range)
    {
        try
        {
            dynamic controls = range.ContentControls;
            int count = Convert.ToInt32(controls.Count);
            for (int i = 1; i <= count; i++)
            {
                dynamic control = controls.Item(i);
                if (IsManagedControl(control))
                {
                    return control;
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private static object? TryGetFirstManagedContentControlInNumberedTable(dynamic range)
    {
        try
        {
            dynamic tables = range.Tables;
            int tableCount = Convert.ToInt32(tables.Count);
            for (int i = 1; i <= tableCount; i++)
            {
                dynamic table = tables.Item(i);
                dynamic controls = table.Range.ContentControls;
                int controlCount = Convert.ToInt32(controls.Count);
                for (int j = 1; j <= controlCount; j++)
                {
                    dynamic control = controls.Item(j);
                    if (IsManagedControl(control))
                    {
                        return control;
                    }
                }
            }
        }
        catch
        {
        }

        return null;
    }

    private static bool IsManagedControl(dynamic control)
    {
        try
        {
            return !string.IsNullOrWhiteSpace(GetManagedEquationId(control));
        }
        catch
        {
            return false;
        }
    }

    private static string GetEquationId(dynamic control)
    {
        return GetManagedEquationId(control);
    }

    private static string GetEquationControlId(dynamic control)
    {
        string tag = Convert.ToString(control.Tag) ?? string.Empty;
        return WordFormulaMetadataStore.EquationIdFromTag(tag);
    }

    private static string GetManagedEquationId(dynamic control)
    {
        string tag = Convert.ToString(control.Tag) ?? string.Empty;
        string equationId = WordFormulaMetadataStore.EquationIdFromTag(tag);
        if (!string.IsNullOrWhiteSpace(equationId))
        {
            return equationId;
        }

        equationId = WordFormulaMetadataStore.EquationIdFromNumberTag(tag);
        return string.IsNullOrWhiteSpace(equationId)
            ? WordFormulaMetadataStore.EquationIdFromMetadataTag(tag)
            : equationId;
    }

    private static bool IsEquationControl(dynamic control)
    {
        try
        {
            string tag = Convert.ToString(control.Tag) ?? string.Empty;
            return !string.IsNullOrWhiteSpace(WordFormulaMetadataStore.EquationIdFromTag(tag));
        }
        catch
        {
            return false;
        }
    }

    private static void ValidateManagedEquationInput(string ooxml, FormulaMetadata metadata)
    {
        if (string.IsNullOrWhiteSpace(ooxml))
        {
            throw new ArgumentException("OOXML is required.", nameof(ooxml));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }
    }
}
