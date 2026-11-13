#if NET48
using System;
using System.Collections.Generic;
using System.Drawing.Text;
using System.Linq;

namespace LaTeXSnipper.OfficePlugin.Editor;

public static class TypographySystemFonts
{
    private static readonly Lazy<string[]> Installed = new Lazy<string[]>(ReadInstalled);
    private static readonly (string Id, string Label)[] ChineseFonts =
    {
        ("DengXian", "等线"),
        ("DengXian Light", "等线 Light"),
        ("FZShuTi", "方正舒体"),
        ("FZYaoTi", "方正姚体"),
        ("FangSong", "仿宋"),
        ("SimHei", "黑体"),
        ("STCaiyun", "华文彩云"),
        ("STFangsong", "华文仿宋"),
        ("STHupo", "华文琥珀"),
        ("STKaiti", "华文楷体"),
        ("STLiti", "华文隶书"),
        ("STSong", "华文宋体"),
        ("STXihei", "华文细黑"),
        ("STXinwei", "华文新魏"),
        ("STXingkai", "华文行楷"),
        ("STZhongsong", "华文中宋"),
        ("KaiTi", "楷体"),
        ("LiSu", "隶书"),
        ("SimSun", "宋体"),
        ("Microsoft YaHei", "微软雅黑"),
        ("Microsoft YaHei Light", "微软雅黑 Light"),
        ("NSimSun", "新宋体"),
        ("YouYuan", "幼圆"),
    };

    public static string[] List() => (string[])Installed.Value.Clone();

    public static Dictionary<string, string>[] ListCjk() => ChineseFonts.Select(font =>
        new Dictionary<string, string> { ["id"] = font.Id, ["label"] = font.Label }).ToArray();

    private static string[] ReadInstalled()
    {
        using var installed = new InstalledFontCollection();
        var families = installed.Families;
        try
        {
            return families.Select(font => font.Name).Distinct().OrderBy(name => name).ToArray();
        }
        finally { foreach (var family in families) family.Dispose(); }
    }
}
#endif
