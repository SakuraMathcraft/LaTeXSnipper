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
                ? "将选区中的普通 OLE 公式逐项转换为 MathType 原生公式，需要安装 MathType。失败项保留原公式并继续处理其余公式。转换后由 MathType 独立排版和编辑，不再保留 LaTeXSnipper 源码与字体快照。"
                : "Convert selected unnumbered OLE formulas to native MathType equations. MathType must be installed. Failed items are preserved and remaining items continue. MathType owns layout and editing after conversion; the LaTeXSnipper source and font snapshot are not retained.",
            "MathTypeOleRequired" => zh ? "请先选择一个 LaTeXSnipper OLE 公式。" : "Select a LaTeXSnipper OLE formula first.",
            "MathTypeNumberedUnsupported" => zh ? "带编号公式暂不支持转为 MathType；请选择普通 OLE 公式。" : "MathType conversion currently requires an unnumbered OLE formula.",
            "MathTypeNativeRequired" => zh ? "宿主未创建 MathType 原生公式，已保留原公式。" : "The host did not create a native MathType equation. The original formula was preserved.",
            _ => throw new System.ArgumentException("Unknown MathType text: " + key, nameof(key))
        };
    }
}
