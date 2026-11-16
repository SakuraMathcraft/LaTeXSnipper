using System;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class VisibleWordStatusSink : IWordStatusSink
{
    private readonly IWordStatusSink _inner;
    private readonly Action _ensureVisible;

    public VisibleWordStatusSink(IWordStatusSink inner, Action ensureVisible)
    {
        _inner = inner ?? throw new ArgumentNullException(nameof(inner));
        _ensureVisible = ensureVisible ?? throw new ArgumentNullException(nameof(ensureVisible));
    }

    public void Post(WordStatusKind kind, string message)
    {
        _ensureVisible();
        _inner.Post(kind, message);
    }

    public void SetBusy(bool busy)
    {
        _inner.SetBusy(busy);
    }

    public void SetOcrActive(bool active)
    {
        if (active)
        {
            _ensureVisible();
        }

        _inner.SetOcrActive(active);
    }

    public void SetCurrentFormula(string latex, bool updateMode)
    {
        _inner.SetCurrentFormula(latex, updateMode);
    }
}
