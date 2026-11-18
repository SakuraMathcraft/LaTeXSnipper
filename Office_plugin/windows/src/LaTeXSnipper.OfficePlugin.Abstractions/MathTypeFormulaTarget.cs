namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>A captured host location; MathType content is read per item so a failed import does not stop the batch.</summary>
public sealed class MathTypeFormulaTarget
{
    public MathTypeFormulaTarget(object document, string documentId, int location, int containerIndex = 0, object? anchor = null)
    {
        Document = document;
        DocumentId = documentId;
        Location = location;
        ContainerIndex = containerIndex;
        Anchor = anchor;
    }

    public object Document { get; }
    public string DocumentId { get; }
    public int Location { get; }
    public int ContainerIndex { get; }
    public object? Anchor { get; }
}
