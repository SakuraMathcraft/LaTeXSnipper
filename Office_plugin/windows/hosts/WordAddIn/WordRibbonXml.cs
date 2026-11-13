using System;
using System.IO;
using System.Security;
using System.Text.RegularExpressions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public static class WordRibbonXml
{
    private static readonly Regex PlaceholderPattern = new(@"\{(?<key>[A-Za-z0-9]+)\}", RegexOptions.Compiled);

    public static string GetCustomUI()
    {
        using Stream? stream = typeof(WordRibbonXml).Assembly.GetManifestResourceStream("LaTeXSnipper.OfficePlugin.WordAddIn.Ribbon.WordRibbon.xml");
        if (stream == null)
        {
            throw new InvalidOperationException("Word 功能区资源缺失，请重新安装插件。");
        }

        using var reader = new StreamReader(stream);
        string template = reader.ReadToEnd();
        return PlaceholderPattern.Replace(template, match => SecurityElement.Escape(WordAddInText.Get(match.Groups["key"].Value)) ?? string.Empty);
    }
}
