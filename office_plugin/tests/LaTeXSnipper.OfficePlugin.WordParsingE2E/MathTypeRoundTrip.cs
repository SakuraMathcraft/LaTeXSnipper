using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class MathTypeRoundTrip
{
    public static async Task VerifyAsync(object application, string output)
    {
        dynamic word = application;
        dynamic document = word.Documents.Add();
        var adapter = new DynamicWordApplicationAdapter(application);
        string runtimeId = Guid.NewGuid().ToString("N");
        using var renderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("MathTypeE2E-" + runtimeId));
        using var controller = WordAddInFactory.CreateController(application, applicationAdapter: adapter,
            mathJaxHostName: "MathTypeControllerE2E-" + runtimeId);
        var examples = new[] {
            (Source: @"\frac{x}{y}+\text{端}", Element: "mfrac"),
            (Source: @"\textcolor{#ff0000}{e^{i\pi}+1=0}", Element: "msup"),
            (Source: @"\sqrt{x+1}", Element: "msqrt"),
            (Source: @"\begin{pmatrix}a&b\\c&d\end{pmatrix}", Element: "mtable"),
            (Source: @"\int_0^1 x\,dx", Element: "msubsup"),
            (Source: @"\textcolor{red}{x}+\mathbf{B}", Element: "mi"),
            (Source: @"\textcolor{#d52020}{\mu(n)=\begin{cases}1,&n=1\\(-1)^k,&n=p_1\cdots p_k\\0,&p^2\mid n\end{cases}}", Element: "mtable")
        };
        var sizes = new (float Width, float Height)[examples.Length];
        try
        {
            foreach (var example in examples)
            {
                Console.WriteLine("STAGE|MathType sample " + example.Element + ": render");
                var metadata = new FormulaMetadata(new FormulaIdentity(adapter.GetCurrentDocumentId(), Guid.NewGuid().ToString("N")),
                    example.Source, FormulaDisplayMode.Inline, NumberingMode.None, "", RenderEngineKind.MathJaxSvg,
                    FormulaMetadata.CurrentSchemaVersion, FormulaTypography.Default);
                var svg = await renderer.RenderAsync(new RenderRequest(metadata.Latex, metadata.DisplayMode, metadata.RenderEngine, metadata.Typography), CancellationToken.None);
                var emf = await new EnhancedMetafilePresentationRenderer().RenderPresentationAsync(new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), CancellationToken.None);
                Console.WriteLine("STAGE|MathType sample: insert LaTeXSnipper OLE");
                await adapter.InsertOleFormulaObjectAsync(metadata, emf, false, CancellationToken.None);
                dynamic shape = document.InlineShapes.Item(document.InlineShapes.Count);
                sizes[Array.IndexOf(examples, example)] = (Convert.ToSingle(shape.Width), Convert.ToSingle(shape.Height));
                shape.Range.Select();
                word.Selection.Collapse(0);
                word.Selection.TypeParagraph();
            }
            document.Content.Select();
            Console.WriteLine("STAGE|MathType: batch conversion from worker thread, first target fails");
            string failedId = (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).First().Metadata!.Identity.EquationId;
            var status = new RecordingStatusSink();
            using (var failing = WordAddInFactory.CreateController(application, statusSink: status,
                applicationAdapter: FailingWordAdapter.Wrap(adapter, failedId), mathJaxHostName: "MathTypeBatchFailure-" + runtimeId))
            {
                await Task.Run(() => failing.ConvertSelectedToMathTypeAsync(CancellationToken.None));
            }
            E2EAssert.True(status.Entries.Last().Message.Contains("Injected MathType conversion failure"), "MathType batch did not report failure");
            E2EAssert.Equal(1, (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Count, "MathType batch stopped after first failure");
            document.Content.Select();
            await Task.Run(() => controller.ConvertSelectedToMathTypeAsync(CancellationToken.None));
            for (int i = 0; i < examples.Length; i++) VerifyShape(document.InlineShapes.Item(i + 1), examples[i].Source, examples[i].Element, sizes[i]);
            string path = Path.Combine(Path.GetDirectoryName(output)!, "word-mathtype.docx");
            document.SaveAs2(path, 16);
            document.Close(0);
            document = word.Documents.Open(path);
            for (int i = 0; i < examples.Length; i++) VerifyShape(document.InlineShapes.Item(i + 1), examples[i].Source, examples[i].Element, sizes[i]);
            document.ExportAsFixedFormat(Path.ChangeExtension(path, ".pdf"), 17);
            // Change native MathType content, then import it through the existing OLE batch command.
            string changed = await renderer.ConvertTypographyToMathMlAsync(@"z^2+\text{新}", FormulaDisplayMode.Inline, FormulaTypography.Default, CancellationToken.None);
            document.InlineShapes.Item(1).OLEFormat.Activate();
            object server = document.InlineShapes.Item(1).OLEFormat.Object;
            try { MathTypeOleBridge.WriteMathMl(server, changed); }
            finally { Marshal.ReleaseComObject(server); }
            document.Content.Select();
            status = new RecordingStatusSink();
            string failedStart = Convert.ToInt32(document.InlineShapes.Item(examples.Length).Range.Start).ToString();
            using (var failing = WordAddInFactory.CreateController(application, statusSink: status,
                applicationAdapter: FailingWordAdapter.Wrap(adapter, failedStart), mathJaxHostName: "MathTypeImportFailure-" + runtimeId))
                await Task.Run(() => failing.ConvertSelectedToOleAsync(CancellationToken.None));
            E2EAssert.True(status.Entries.Last().Message.Contains("Injected MathType import failure"), "MathType import batch did not report concrete failure");
            E2EAssert.Equal(examples.Length - 1, (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Count, "MathType import did not continue after first failure");
            document.Content.Select();
            await Task.Run(() => controller.ConvertSelectedToOleAsync(CancellationToken.None));
            var imported = await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None);
            E2EAssert.Equal(examples.Length, imported.Count, "Mixed OLE/MathType selection did not finish importing");
            var edited = imported.Single(e => XDocument.Parse(e.Metadata!.Latex).Root!.Value.Contains("新"));
            E2EAssert.True(XDocument.Parse(edited.Metadata!.Latex).Root!.Value.Contains("z"), "Import restored stale content instead of edited MathType content");
            document.SaveAs2(Path.Combine(Path.GetDirectoryName(output)!, "word-mathtype-import.docx"), 16);
            Console.WriteLine("PASS|Word MathType to OLE: current edited content, mixed selection, first failure continues, worker thread");
            Console.WriteLine("PASS|MathType native fraction, Chinese, superscript, root, matrix, integral and styles; Word save/reopen");
        }
        finally { document.Close(0); }
    }

    private static void VerifyShape(dynamic shape, string source, string element, (float Width, float Height) size)
    {
        E2EAssert.Equal(MathTypeOleBridge.ProgId, Convert.ToString(shape.OLEFormat.ProgID), "MathType class identity");
        E2EAssert.True(Math.Abs(Convert.ToSingle(shape.Width) - size.Width) <= Math.Max(0.5f, size.Width * 0.01f)
            && Math.Abs(Convert.ToSingle(shape.Height) - size.Height) <= Math.Max(0.5f, size.Height * 0.01f),
            "MathType changed the original object's width or height");
        shape.OLEFormat.Activate();
        object server = shape.OLEFormat.Object;
        string mathMl;
        try
        {
            mathMl = MathTypeOleBridge.ReadAndCloseMathMl(server);
        }
        finally { Marshal.ReleaseComObject(server); }
        var xml = XDocument.Parse(mathMl);
        Console.WriteLine("MATHTYPE|" + source + "|" + mathMl);
        E2EAssert.True(xml.Descendants().Any(e => e.Name.LocalName == element
            || (element == "msubsup" && e.Name.LocalName == "munderover")), "MathType lost structure " + element);
        if (element == "msubsup") E2EAssert.True(xml.Root!.Value.Contains("∫")
            && xml.Root.Value.Contains("0") && xml.Root.Value.Contains("1"), "MathType lost integral bounds");
        if (source.Contains("端")) E2EAssert.True(xml.Root!.Value.Contains("端"), "MathType lost Chinese text");
    }
}
