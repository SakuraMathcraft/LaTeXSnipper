using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class WordSurroundingFormatting
{
    public static async Task VerifyAsync(object application, WordPluginSettings settings, string output)
    {
        dynamic word = application;
        using var renderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("SurroundingFormatting"));
        var token = CancellationToken.None;
        var svg = await renderer.RenderAsync(new RenderRequest("x^2", FormulaDisplayMode.Inline,
            RenderEngineKind.MathJaxSvg, FormulaTypography.Default), token);
        var emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(
            new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), token);
        byte[] native = MathTypeNativeEquation.Create("<math xmlns='http://www.w3.org/1998/Math/MathML'><msup><mi>x</mi><mn>2</mn></msup></math>", 12);
        string package = MathTypeWordPackage.Create(MathTypeCompoundFile.Create(native), emf,
            (float)emf.WidthPoints, (float)emf.HeightPoints);
        foreach (bool inTable in new[] { false, true })
        {
            dynamic? document = word.Documents.Add();
            using var adapter = new DynamicWordApplicationAdapter(application);
            using var controller = WordAddInFactory.CreateController(application,
                optionsProvider: new TestFormulaOptionsProvider { CurrentLatex = "x+1" },
                settingsLoader: () => settings, applicationAdapter: adapter,
                mathJaxHostName: "SurroundingController-" + Guid.NewGuid().ToString("N"));
            try
            {
                dynamic insertion = inTable ? document.Tables.Add(document.Range(0, 0), 1, 1).Cell(1, 1).Range : document.Range(0, 0);
                insertion.Collapse(1);
                insertion.InsertXML(package);
                dynamic neighbor = document.InlineShapes.Item(1);
                neighbor.Range.Font.Position = -5;
                float width = Convert.ToSingle(neighbor.Width), height = Convert.ToSingle(neighbor.Height);
                string originalMath = MathTypeNativeEquation.ReadMathMl(MathTypeWordPackage.ReadNative(Convert.ToString(neighbor.Range.WordOpenXML)!));
                int end = Convert.ToInt32(neighbor.Range.End);
                document.Range(end, end).Text = " UP  DOWN RAISED $y$";
                document.Bookmarks.Add("KeepUp", document.Range(end + 1, end + 3));
                document.Bookmarks.Add("KeepDown", document.Range(end + 5, end + 9));
                document.Bookmarks.Add("KeepRaised", document.Range(end + 10, end + 16));
                document.Bookmarks.Item("KeepUp").Range.Font.Superscript = -1;
                document.Bookmarks.Item("KeepDown").Range.Font.Subscript = -1;
                document.Bookmarks.Item("KeepRaised").Range.Font.Position = 3;
                await controller.ParseAllAsync(token);
                Verify(document, width, height, originalMath, "parse");
                E2EAssert.Equal(1, (await adapter.LoadFormulaEntriesAsync(true, token)).Count, "Parsed formula count");
                int cursor = Convert.ToInt32(document.Bookmarks.Item("KeepDown").Range.Start) - 1;
                word.Selection.SetRange(cursor, cursor);
                await controller.InsertOmmlAsync(token);
                Verify(document, width, height, originalMath, "insert");
                E2EAssert.Equal(2, (await adapter.LoadFormulaEntriesAsync(true, token)).Count, "Parsed formula count");
                await controller.FormatAllAsync(token);
                Verify(document, width, height, originalMath, "format/update");
                foreach (bool toOle in settings.InsertionBackend == FormulaInsertionBackend.Ole
                    ? new[] { false, true } : new[] { false })
                {
                    foreach (var entry in (await adapter.LoadFormulaEntriesAsync(true, token)).OrderByDescending(e => e.Start))
                    {
                        word.Selection.SetRange(entry.Start, entry.Start + 1);
                        if (toOle) await controller.ConvertSelectedToOleAsync(token);
                        else await controller.ConvertSelectedToOmmlAsync(token);
                    }
                    Verify(document, width, height, originalMath, toOle ? "convert to OLE" : "convert to OMML");
                    var engine = toOle ? RenderEngineKind.MathJaxSvg : RenderEngineKind.Omml;
                    E2EAssert.True((await adapter.LoadFormulaEntriesAsync(true, token)).All(e => e.Metadata!.RenderEngine == engine), "Conversion backend");
                }
                string path = Path.Combine(Path.GetDirectoryName(output)!, $"surrounding-{settings.InsertionBackend}-{inTable}.docx");
                document.SaveAs2(path, 16);
                document.Close(0);
                document = null;
                document = word.Documents.Open(path);
                Verify(document, width, height, originalMath, "reopen");
                document.Bookmarks.Item("KeepUp").Range.Select();
                await adapter.ActivateForEditingAsync(token);
                Verify(document, width, height, originalMath, "focus");
                Console.WriteLine($"PASS|Surrounding MathType, superscript, subscript, raised text|{settings.InsertionBackend}|table={inTable}");
            }
            finally { if (document != null) document.Close(0); }
        }
    }

    private static void Verify(dynamic document, float width, float height, string originalMath, string stage)
    {
        dynamic neighbor = document.InlineShapes.Item(1);
        E2EAssert.Equal(MathTypeOleBridge.ProgId, Convert.ToString(neighbor.OLEFormat.ProgID), stage + " MathType identity");
        // An OLE range also includes hidden field-code runs, whose formatting can differ after reopening.
        XNamespace w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
        var xml = XDocument.Parse(Convert.ToString((object)neighbor.Range.WordOpenXML)!);
        var objectRun = xml.Descendants(w + "r").Single(r => r.Element(w + "object") != null);
        E2EAssert.Equal("-10", (string?)objectRun.Element(w + "rPr")?.Element(w + "position")?.Attribute(w + "val"), stage + " MathType baseline");
        E2EAssert.True(Math.Abs(Convert.ToSingle(neighbor.Width) - width) < 0.1 && Math.Abs(Convert.ToSingle(neighbor.Height) - height) < 0.1, stage + " MathType size");
        E2EAssert.Equal(originalMath, MathTypeNativeEquation.ReadMathMl(MathTypeWordPackage.ReadNative(Convert.ToString(neighbor.Range.WordOpenXML)!)), stage + " MathType content");
        E2EAssert.Equal(-1, Convert.ToInt32(document.Bookmarks.Item("KeepUp").Range.Font.Superscript), stage + " preceding superscript");
        E2EAssert.Equal(-1, Convert.ToInt32(document.Bookmarks.Item("KeepDown").Range.Font.Subscript), stage + " following subscript");
        E2EAssert.Equal(3, Convert.ToInt32(document.Bookmarks.Item("KeepRaised").Range.Font.Position), stage + " raised text");
    }
}
