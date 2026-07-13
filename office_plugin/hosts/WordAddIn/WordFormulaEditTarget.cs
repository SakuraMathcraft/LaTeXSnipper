using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordFormulaEditTarget
{
    internal WordFormulaEditTarget(
        object document,
        object window,
        object formulaObject,
        int windowHandle,
        FormulaMetadata metadata,
        bool isOle,
        double fontSizePoints)
    {
        Document = document ?? throw new ArgumentNullException(nameof(document));
        Window = window ?? throw new ArgumentNullException(nameof(window));
        FormulaObject = formulaObject ?? throw new ArgumentNullException(nameof(formulaObject));
        WindowHandle = windowHandle;
        Metadata = metadata ?? throw new ArgumentNullException(nameof(metadata));
        IsOle = isOle;
        FontSizePoints = fontSizePoints;
    }

    internal object Document { get; }

    internal object Window { get; }

    internal object FormulaObject { get; }

    public int WindowHandle { get; }

    public FormulaMetadata Metadata { get; }

    public bool IsOle { get; }

    public double FontSizePoints { get; }
}
