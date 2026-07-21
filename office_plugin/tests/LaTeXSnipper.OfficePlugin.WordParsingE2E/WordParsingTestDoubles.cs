using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal sealed class TestFormulaOptionsProvider : IWordFormulaOptionsProvider
{
    public string CurrentLatex => string.Empty;

    public WordFormulaOptions GetFormulaOptions()
    {
        return new WordFormulaOptions(display: false, NumberingMode.None, string.Empty);
    }

    public void ApplyFormulaMetadata(FormulaMetadata metadata, bool updateMode)
    {
    }

    public void ResetFormulaDraft()
    {
    }
}

internal sealed class RecordingStatusSink : IWordStatusSink
{
    private static readonly Regex BatchProgressPattern = new Regex(
        @"\d+\s*/\s*\d+",
        RegexOptions.CultureInvariant);

    private readonly List<StatusEntry> _entries = new List<StatusEntry>();
    private CancellationTokenSource? _batchCancellation;

    public IReadOnlyList<StatusEntry> Entries => _entries;

    public void CancelAfterNextBatch(CancellationTokenSource cancellation)
    {
        _batchCancellation = cancellation ?? throw new ArgumentNullException(nameof(cancellation));
    }

    public void Post(WordStatusKind kind, string message)
    {
        _entries.Add(new StatusEntry(kind, message));
        Console.WriteLine("STATUS|" + kind + "|" + message);
        if (_batchCancellation != null && BatchProgressPattern.IsMatch(message))
        {
            CancellationTokenSource cancellation = _batchCancellation;
            _batchCancellation = null;
            cancellation.Cancel();
        }
    }

    public void SetBusy(bool busy)
    {
    }

    public void SetOcrActive(bool active)
    {
    }

    public void SetCurrentFormula(string latex, bool updateMode)
    {
    }
}

internal sealed class StatusEntry
{
    public StatusEntry(WordStatusKind kind, string message)
    {
        Kind = kind;
        Message = message ?? string.Empty;
    }

    public WordStatusKind Kind { get; }

    public string Message { get; }
}
