namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal sealed class WordEquationNumberState
{
    public WordEquationNumberState(
        string prefix,
        bool resetSequence,
        WordNumberEnclosure enclosure)
    {
        Prefix = prefix;
        ResetSequence = resetSequence;
        Enclosure = enclosure;
    }

    public string Prefix { get; }

    public bool ResetSequence { get; }

    public WordNumberEnclosure Enclosure { get; }
}
