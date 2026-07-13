using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter : IWordApplicationAdapter
{
    private const double WordOleBaseFontPoints = 10.5;
    private const int WdCollapseEnd = 0;
    private const int WdCharacter = 1;
    private const int WdMove = 0;
    private const int WdAlignParagraphLeft = 0;
    private const int WdAlignParagraphCenter = 1;
    private const int WdAlignTabCenter = 1;
    private const int WdAlignTabRight = 2;
    private const int WdTabLeaderSpaces = 0;
    private const int WdContentControlRichText = 0;
    private const int WdFieldEmpty = -1;
    private const string OleFormulaProgId = "LaTeXSnipper.Formula";

    private readonly dynamic _wordApplication;
    private readonly OmmlToMathMlConverter _ommlToMathMlConverter;
    private int _undoRecordDepth;

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    private sealed class NumberedFormulaEntry
    {
        public NumberedFormulaEntry(
            string equationId,
            object formulaObject,
            FormulaMetadata metadata,
            int start,
            RenderEngineKind renderEngine)
        {
            EquationId = equationId;
            FormulaObject = formulaObject;
            Metadata = metadata;
            Start = start;
            RenderEngine = renderEngine;
        }

        public string EquationId { get; }

        public object FormulaObject { get; }

        public FormulaMetadata Metadata { get; }

        public int Start { get; }

        public RenderEngineKind RenderEngine { get; }
    }

    private sealed class NumberingBoundaryEntry
    {
        public NumberingBoundaryEntry(WordNumberingBoundary boundary, int start)
        {
            Boundary = boundary;
            Start = start;
        }

        public WordNumberingBoundary Boundary { get; }

        public int Start { get; }
    }

    private sealed class NumberingTimelineEntry
    {
        public NumberingTimelineEntry(int start, WordNumberingBoundary? boundary, bool isAutomaticFormula)
        {
            Start = start;
            Boundary = boundary;
            IsAutomaticFormula = isAutomaticFormula;
        }

        public int Start { get; }

        public WordNumberingBoundary? Boundary { get; }

        public bool IsAutomaticFormula { get; }
    }

    private sealed class ManagedRangeSpan
    {
        public ManagedRangeSpan(int start, int end)
        {
            Start = start;
            End = end;
        }

        public int Start { get; }

        public int End { get; }
    }

    private sealed class UndoRecordScope : IDisposable
    {
        private readonly DynamicWordApplicationAdapter _owner;
        private readonly bool _started;
        private bool _disposed;

        public UndoRecordScope(DynamicWordApplicationAdapter owner)
        {
            _owner = owner;
            if (_owner._undoRecordDepth == 0)
            {
                _started = _owner.TryStartUndoRecord();
            }

            _owner._undoRecordDepth++;
        }

        public void Dispose()
        {
            if (_disposed)
            {
                return;
            }

            _disposed = true;
            _owner._undoRecordDepth = Math.Max(0, _owner._undoRecordDepth - 1);
            if (_started && _owner._undoRecordDepth == 0)
            {
                _owner.TryEndUndoRecord();
            }
        }
    }


    public DynamicWordApplicationAdapter(object wordApplication, OmmlToMathMlConverter? ommlToMathMlConverter = null)
    {
        _wordApplication = wordApplication ?? throw new ArgumentNullException(nameof(wordApplication));
        _ommlToMathMlConverter = ommlToMathMlConverter ?? new OmmlToMathMlConverter();
    }

    public double GetCurrentFontSizePoints()
    {
        double fontSize = ReadPointSize(_wordApplication.Selection.Font.Size);
        return fontSize > 0 ? fontSize : WordOleBaseFontPoints;
    }

    public Task ActivateForEditingAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        TryCom(() => _wordApplication.Activate());
        TryCom(() => _wordApplication.ActiveWindow.Activate());
        TryCom(() => _wordApplication.ActiveWindow.SetFocus());
        TryCom(() => SetForegroundWindow(new IntPtr(Convert.ToInt32(_wordApplication.ActiveWindow.Hwnd))));
        TryCom(() => SetForegroundWindow(new IntPtr(Convert.ToInt32(_wordApplication.Hwnd))));
        ResetSelectionFormulaTextFormatting();
        return Task.CompletedTask;
    }

    public IDisposable BeginUndoRecord()
    {
        return new UndoRecordScope(this);
    }

    public string GetCurrentDocumentId()
    {
        return WordDocumentIdentityStore.GetOrCreate(CurrentDocument);
    }

    public Task ValidateCurrentInsertionTargetAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        ValidateInsertionTarget(range);
        return Task.CompletedTask;
    }
}
