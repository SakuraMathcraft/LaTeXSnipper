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
    private const int WdColorAutomatic = -16777216;
    private const double WordOleBaseFontPoints = 10.5;
    private const int WdCollapseEnd = 0;
    private const int WdCharacter = 1;
    private const int WdMove = 0;
    private const int WdAlignParagraphCenter = 1;
    private const int WdAlignTabLeft = 0;
    private const int WdAlignTabCenter = 1;
    private const int WdAlignTabRight = 2;
    private const int WdTabLeaderSpaces = 0;
    private const int WdContentControlRichText = 0;
    private const string OleFormulaProgId = "LaTeXSnipper.Formula";

    private readonly dynamic _wordApplication;
    private int _undoRecordDepth;

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    private sealed class NumberedFormulaEntry
    {
        public NumberedFormulaEntry(
            string equationId,
            object formulaObject,
            object numberControl,
            FormulaMetadata metadata,
            int start)
        {
            EquationId = equationId;
            FormulaObject = formulaObject;
            NumberControl = numberControl;
            Metadata = metadata;
            Start = start;
        }

        public string EquationId { get; }

        public object FormulaObject { get; }

        public object NumberControl { get; }

        public FormulaMetadata Metadata { get; }

        public int Start { get; }
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

    private sealed class IndexedFormulaObject
    {
        public IndexedFormulaObject(object value, RenderEngineKind renderEngine)
        {
            Value = value;
            RenderEngine = renderEngine;
        }

        public object Value { get; }

        public RenderEngineKind RenderEngine { get; }
    }

    private sealed class DeletionTarget
    {
        public DeletionTarget(int start, int end, Action delete)
        {
            Start = start;
            End = end;
            Delete = delete;
        }

        public int Start { get; }

        public int End { get; }

        public Action Delete { get; }
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

    public DynamicWordApplicationAdapter(object wordApplication)
    {
        _wordApplication = wordApplication ?? throw new ArgumentNullException(nameof(wordApplication));
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

    public Task ValidateCurrentInsertionTargetAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        dynamic selection = _wordApplication.Selection;
        dynamic range = selection.Range;
        ValidateInsertionTarget(range);
        return Task.CompletedTask;
    }
}
