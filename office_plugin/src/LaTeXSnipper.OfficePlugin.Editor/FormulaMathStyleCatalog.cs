using System;
using System.Collections.Generic;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Editor;

public static class FormulaMathStyleCatalog
{
    private static readonly (string Chinese, string English)[] Labels =
    {
        ("自动数学样式", "Automatic"),
        ("正体", "Upright"),
        ("粗体", "Bold"),
        ("斜体", "Italic"),
        ("粗斜体", "Bold Italic"),
        ("无衬线", "Sans Serif"),
        ("无衬线粗体", "Sans Serif Bold"),
        ("无衬线斜体", "Sans Serif Italic"),
        ("无衬线粗斜体", "Sans Serif Bold Italic"),
        ("等宽", "Monospace"),
        ("花体", "Calligraphic"),
        ("粗花体", "Bold Calligraphic"),
        ("手写体", "Script"),
        ("粗手写体", "Bold Script"),
        ("哥特体", "Fraktur"),
        ("哥特粗体", "Bold Fraktur"),
        ("双线体", "Blackboard Bold"),
    };

    public static Dictionary<string, string>[] List()
    {
        var values = (FormulaMathStyle[])Enum.GetValues(typeof(FormulaMathStyle));
        if (values.Length != Labels.Length) throw new InvalidOperationException("数学字形选项与数据契约不一致。");
        var result = new Dictionary<string, string>[values.Length];
        for (int index = 0; index < values.Length; index++)
        {
            result[index] = new Dictionary<string, string>
            {
                ["id"] = values[index].ToString(),
                ["zh"] = Labels[index].Chinese,
                ["en"] = Labels[index].English,
            };
        }
        return result;
    }
}
