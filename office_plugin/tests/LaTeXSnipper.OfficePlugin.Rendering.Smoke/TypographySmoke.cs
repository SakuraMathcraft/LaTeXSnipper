using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

internal static class TypographySmoke
{
    public static async Task RunAsync()
    {
        using var runtime = new WebView2MathJaxJavaScriptRuntime("TypographySmoke-" + Guid.NewGuid().ToString("N"));
        using var renderer = new MathJaxSvgRenderer(runtime);
        var results = new List<RenderResult>();
        string align = @"\begin{align}&\text{设 } A,B \text{ 为事件，若 } P(B)>0,\ \text{则称} \\
&\quad P(A\mid B)=\frac{P(A\cap B)}{P(B)} \\
&\text{为在 } B \text{ 发生的条件下 } A \text{ 的条件概率。}\end{align}";
        foreach (string font in new[] { "mathjax-tex", "mathjax-stix2" })
        {
            foreach (string cjk in new[] { "SimSun", "Microsoft YaHei" })
                foreach (FormulaMathStyle style in new[] { FormulaMathStyle.Automatic, FormulaMathStyle.Upright, FormulaMathStyle.Bold })
                    results.Add(await renderer.RenderTypographyAsync(align, FormulaDisplayMode.Display,
                        Style(font, cjk, style), CancellationToken.None));
            foreach (string source in new[] { @"\delta", @"\mathrm{\delta}", @"\mathbf{\delta}",
                @"\frac{123}{45}+6^{78}_{90}+\mathbf{12}+\text{汉字，A 12。}",
                @"\begin{align} A&=\mathbf{B}+\begin{pmatrix}x&\mathrm{y}\\z&\mathit{w}\end{pmatrix}\end{align}",
                @"\ce{2H2 + O2 <=> 2H2O}", @"\text{ office AV 12 }+\textit{j}",
                @"\textcolor{red}{x}+y", @"\sum_{i=1}^{12}\left(\frac{a}{b}\right)" })
                results.Add(await renderer.RenderTypographyAsync(source, FormulaDisplayMode.Display,
                    Style(font), CancellationToken.None));
            foreach (FormulaMathStyle style in Enum.GetValues(typeof(FormulaMathStyle)))
                results.Add(await renderer.RenderTypographyAsync(@"A+x+12+\delta+\Gamma", FormulaDisplayMode.Display,
                    Style(font, style: style), CancellationToken.None));
        }
        var serializer = new JavaScriptSerializer();
        results.Add(await renderer.RenderTypographyAsync("<?xml version=\"1.0\"?><math xmlns=\"http://www.w3.org/1998/Math/MathML\"><mfrac><mi mathvariant=\"normal\">δ</mi><mi>x</mi></mfrac></math>",
            FormulaDisplayMode.Display, Style(), CancellationToken.None));
        foreach (RenderResult result in results)
        {
            string svg = Encoding.UTF8.GetString(result.Payload);
            Check(!XElement.Parse(svg).Descendants().Any(e => e.Name.LocalName == "text"), "SVG text fallback");
            string geometry = await runtime.EvaluateAsync(@"(() => {
                const svg = new DOMParser().parseFromString(" + serializer.Serialize(svg) + @", 'image/svg+xml').documentElement;
                const e = document.importNode(svg, true); document.body.appendChild(e);
                try {
                    const b = e.getBBox(), v = e.viewBox.baseVal;
                    if (b.x < v.x-2 || b.y < v.y-2 || b.x+b.width > v.x+v.width+2 || b.y+b.height > v.y+v.height+2)
                        throw new Error('Clipped SVG: ' + JSON.stringify({x:b.x,y:b.y,w:b.width,h:b.height,viewBox:e.getAttribute('viewBox')}));
                    for (const f of e.querySelectorAll('[data-mml-node=mfrac]'))
                        if (f.children[0].getBoundingClientRect().bottom > f.children[1].getBoundingClientRect().top + .1)
                            throw new Error('Overlapping fraction');
                    for (const s of e.querySelectorAll('[data-mml-node=msubsup]'))
                        if (s.children[1].getBoundingClientRect().bottom > s.children[2].getBoundingClientRect().top + .1)
                            throw new Error('Overlapping scripts');
                    return {ok:true};
                } finally { e.remove(); }
            })()", CancellationToken.None);
            Check(geometry == "{\"ok\":true}", geometry);
            OlePresentationResult emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
                new OlePresentationRequest(result, OlePresentationKind.EnhancedMetafile), CancellationToken.None);
            VerifyVectorMetafile(emf.Payload);
            foreach (int dpi in new[] { 96, 300 })
            {
                using var stream = new MemoryStream(SvgPngRasterizer.Rasterize(result, CancellationToken.None, dpi));
                using var bitmap = new Bitmap(stream);
                Check(bitmap.Width == (int)Math.Ceiling(result.WidthPoints / 72 * dpi), "PNG physical width");
            }
        }
        const string sample = @"\mathrm{\delta}+\text{汉字}";
        RenderResult first = await renderer.RenderTypographyAsync(sample, FormulaDisplayMode.Display, Style(), CancellationToken.None);
        RenderResult same = await renderer.RenderTypographyAsync(sample, FormulaDisplayMode.Display, Style(), CancellationToken.None);
        RenderResult larger = await renderer.RenderTypographyAsync(sample, FormulaDisplayMode.Display, Style().WithFontSize(24), CancellationToken.None);
        Check(ReferenceEquals(first, same), "Typography cache hit");
        Check(Math.Abs(larger.WidthPoints - first.WidthPoints * 2) < .0001
            && Math.Abs(larger.HeightPoints - first.HeightPoints * 2) < .0001, "Absolute point scaling");
        string mml = await renderer.ConvertTypographyToMathMlAsync(@"A+\mathrm{\delta}+\mathbf{B}+\textcolor{red}{x}",
            FormulaDisplayMode.Display, Style(style: FormulaMathStyle.Bold), CancellationToken.None);
        XElement delta = XElement.Parse(mml).Descendants().Single(e => e.Name.LocalName == "mi" && e.Value == "δ");
        Check((string?)delta.Attribute("mathvariant") == "normal", "MathML local upright Greek");
        Check(mml.Contains("red"), "MathML local color");
        const string labeled = @"x=1\label{eq:repeat}";
        string labeledMathMl = await renderer.ConvertTypographyToMathMlAsync(labeled,
            FormulaDisplayMode.Display, Style(), CancellationToken.None);
        string repeatedMathMl = await renderer.ConvertTypographyToMathMlAsync(labeled,
            FormulaDisplayMode.Display, Style(), CancellationToken.None);
        Check(labeledMathMl == repeatedMathMl, "Repeated conversion retained equation labels");
        await renderer.RenderTypographyAsync(labeled, FormulaDisplayMode.Display, Style(), CancellationToken.None);
        await renderer.RenderTypographyAsync(labeled, FormulaDisplayMode.Display,
            Style(style: FormulaMathStyle.Bold), CancellationToken.None);
        string omml = OmmlTypographyMapper.Apply(new LaTeXSnipper.OfficePlugin.WordAddIn.MathMlToOmmlConverter().Convert(mml), Style());
        XNamespace word = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
        XNamespace officeMath = "http://schemas.openxmlformats.org/officeDocument/2006/math";
        XElement native = XElement.Parse(omml);
        Check(native.Descendants(word + "sz").Any(e => (string?)e.Attribute(word + "val") == "24"), "OMML point size mapping");
        Check(native.Descendants(officeMath + "t").Any(e => e.Value.Contains("δ")), "OMML content lost");
        RenderResult upright = await renderer.RenderTypographyAsync(@"\mathrm{\delta}", FormulaDisplayMode.Display, Style(), CancellationToken.None);
        RenderResult italic = await renderer.RenderTypographyAsync(@"\delta", FormulaDisplayMode.Display, Style(), CancellationToken.None);
        string[] Paths(RenderResult result) => XElement.Parse(Encoding.UTF8.GetString(result.Payload)).Descendants()
            .Where(e => e.Name.LocalName == "path").Select(e => (string)e.Attribute("d")!).ToArray();
        Check(!Paths(upright).SequenceEqual(Paths(italic)), "Upright Greek still uses the italic glyph");

        var outlines = new SystemFontOutlineService();
        FontRunOutline a = outlines.Shape("AV", "Times New Roman", FontRunStyle.Regular);
        FontRunOutline spaced = outlines.Shape("AV ", "Times New Roman", FontRunStyle.Regular);
        Check(spaced.Advance > a.Advance, "Trailing space lost");
        foreach (var pair in new[] { (Source: @"\textbf{AV}", Style: FontRunStyle.Bold),
            (Source: @"\textit{AV}", Style: FontRunStyle.Italic) })
        {
            RenderResult styledText = await renderer.RenderTypographyAsync(pair.Source, FormulaDisplayMode.Display,
                Style(), CancellationToken.None);
            string path = outlines.Shape("AV", "Times New Roman", pair.Style).Path;
            Check(XElement.Parse(Encoding.UTF8.GetString(styledText.Payload)).Descendants()
                .Any(e => e.Name.LocalName == "path" && (string?)e.Attribute("d") == path), "Local text style lost: " + pair.Source);
        }
        FontRunOutline fallback = outlines.Shape("字", "LaTeXSnipper Missing Test Font", FontRunStyle.Regular, new[] { "SimSun" });
        Check(fallback.Warning != null && fallback.ActualFamily == "SimSun", "Missing font diagnostic");
        try { outlines.Shape("字", "Times New Roman", FontRunStyle.Regular); throw new Exception("Missing glyph accepted"); }
        catch (InvalidOperationException) { }
        using (var cancelled = new CancellationTokenSource())
        {
            cancelled.Cancel();
            try { await renderer.RenderTypographyAsync("x", FormulaDisplayMode.Display, Style(), cancelled.Token); throw new Exception("Cancellation ignored"); }
            catch (OperationCanceledException) { }
        }
        RenderResult[] simultaneous = await Task.WhenAll(
            renderer.RenderTypographyAsync("x", FormulaDisplayMode.Display, Style(style: FormulaMathStyle.Bold), CancellationToken.None),
            renderer.RenderAsync(new RenderRequest("x", FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg, FormulaTypography.Default), CancellationToken.None),
            renderer.RenderTypographyAsync("x", FormulaDisplayMode.Display, Style("mathjax-stix2"), CancellationToken.None));
        Check(!simultaneous[0].Payload.SequenceEqual(simultaneous[1].Payload), "Concurrent style isolation");
        Console.WriteLine($"Typography passed: {results.Count} SVG/EMF samples, {results.Count * 2} PNG outputs, MathML, cache, sizes and font diagnostics.");
    }

    private static FormulaTypography Style(string font = "mathjax-tex", string cjk = "SimSun",
        FormulaMathStyle style = FormulaMathStyle.Automatic) => new FormulaTypography(font, "Times New Roman", cjk, style, 12, "#000000");

    private static void Check(bool value, string message)
    {
        if (!value) throw new InvalidOperationException(message);
    }

    private static void VerifyVectorMetafile(byte[] payload)
    {
        using var stream = new MemoryStream(payload);
        using var metafile = new Metafile(stream);
        using var bitmap = new Bitmap(1, 1);
        using var graphics = Graphics.FromImage(bitmap);
        bool hasPath = false, hasText = false;
        graphics.EnumerateMetafile(metafile, Point.Empty, (type, flags, size, data, callbackData) =>
        {
            hasPath |= type == EmfPlusRecordType.FillPath || type == EmfPlusRecordType.EmfFillPath;
            hasText |= type.ToString().Contains("TextOut") || type == EmfPlusRecordType.DrawString || type == EmfPlusRecordType.DrawDriverString;
            return true;
        });
        Check(hasPath && !hasText, "EMF must contain outlines without text records");
    }
}
