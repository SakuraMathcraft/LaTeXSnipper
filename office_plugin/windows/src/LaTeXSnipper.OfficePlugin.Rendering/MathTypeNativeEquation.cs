using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Encodes and reads current MathType MTEF v5 content without an equation server.</summary>
public static class MathTypeNativeEquation
{
    public static byte[] Create(string mathMl, double fontSizePoints)
    {
        var math = XDocument.Parse(mathMl);
        var size = math.Descendants().Attributes("mathsize").FirstOrDefault(a => a.Value != "normal");
        if (size != null) throw new InvalidDataException("MathType encoding does not support local mathsize=" + size.Value + "; the original equation was retained.");
        var result = MathTypeMtefCodec.CreateEquationNativeAtFontSize(mathMl, fontSizePoints);
        string decoded = ReadMathMl(result);
        if (MathTypeMtefCodec.SemanticSignature(mathMl) != MathTypeMtefCodec.SemanticSignature(decoded))
            throw new InvalidDataException("MathType MTEF semantic validation failed; the original equation was retained.");
        if (Math.Abs(ReadFontSizePoints(result) - fontSizePoints) > 0.001)
            throw new InvalidDataException("MathType MTEF font size validation failed.");
        return result;
    }

    public static string ReadMathMl(byte[] equationNative) => MathTypeMtefCodec.ReadEquationNativeMathMl(equationNative);

    public static double ReadFontSizePoints(byte[] equationNative) => MathTypeMtefCodec.ReadEquationNativeFullFontSize(equationNative);
}
