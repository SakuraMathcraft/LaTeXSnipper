using System;
using System.IO;
using System.Security;
using System.Text.RegularExpressions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointRibbonXml
{
    private static readonly Regex PlaceholderPattern = new(@"\{(?<key>[A-Za-z0-9]+)\}", RegexOptions.Compiled);

    public static string GetCustomUI()
    {
        using Stream? stream = typeof(PowerPointRibbonXml).Assembly.GetManifestResourceStream("LaTeXSnipper.OfficePlugin.PowerPointAddIn.Ribbon.PowerPointRibbon.xml");
        if (stream == null)
        {
            throw new InvalidOperationException("PowerPoint Ribbon XML resource is missing.");
        }

        using var reader = new StreamReader(stream);
        string template = reader.ReadToEnd();
        return PlaceholderPattern.Replace(template, match => SecurityElement.Escape(PowerPointAddInText.Get(match.Groups["key"].Value)) ?? string.Empty);
    }
}
