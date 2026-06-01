using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal sealed class OleFormulaPresentation
{
    public OleFormulaPresentation(OleFormulaPayload payload, byte[] enhancedMetafile)
    {
        Payload = payload;
        EnhancedMetafile = enhancedMetafile;
    }

    public OleFormulaPayload Payload { get; }

    public byte[] EnhancedMetafile { get; }
}
