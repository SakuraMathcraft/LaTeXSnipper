using System.Globalization;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public static class MathTypeText
{
    public static string Get(string key)
    {
        bool zh = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName == "zh";
        return key switch
        {
            "ToMathTypeButton" => zh ? "转为 MathType" : "To MathType",
            "ToMathTypeTip" => zh
                ? "将所选 OLE 公式转为 MathType 公式。"
                : "Convert selected OLE formulas to MathType equations.",
            "MathTypeOleRequired" => zh ? "请先选择一个 LaTeXSnipper OLE 公式。" : "Select a LaTeXSnipper OLE formula first.",
            "MathTypeNumberedUnsupported" => zh ? "带编号公式暂不支持转为 MathType；请选择普通 OLE 公式。" : "MathType conversion currently requires an unnumbered OLE formula.",
            "MathTypeNativeRequired" => zh ? "宿主未创建 MathType 原生公式，已保留原公式。" : "The host did not create a native MathType equation. The original formula was preserved.",
            _ => throw new System.ArgumentException("Unknown MathType text: " + key, nameof(key))
        };
    }
}
