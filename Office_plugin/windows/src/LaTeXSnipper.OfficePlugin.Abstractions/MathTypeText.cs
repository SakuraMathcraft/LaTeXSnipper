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
            "WordMathTypeUnsupported" => zh
                ? "Word 公式无法直接转为 MathType。请先转为 OLE。"
                : "Word equations must be converted to OLE before converting to MathType.",
            "PowerPointMathTypeUnsupported" => zh
                ? "PNG 公式无法直接转为 MathType。请先转为 OLE。"
                : "PNG formulas must be converted to OLE before converting to MathType.",
            "MathTypeNativeRequired" => zh ? "宿主未创建 MathType 原生公式，已保留原公式。" : "The host did not create a native MathType equation. The original formula was preserved.",
            "MathTypeInsertingStatus" => zh ? "正在插入 MathType 公式。" : "Inserting MathType equation.",
            "MathTypeInsertedStatus" => zh ? "已插入 MathType 公式。" : "Inserted MathType equation.",
            _ => throw new System.ArgumentException("Unknown MathType text: " + key, nameof(key))
        };
    }
}
