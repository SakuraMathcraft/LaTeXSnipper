using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using System.Drawing;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;
using LaTeXSnipper.OfficePlugin.Testing;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static partial class MathTypeRoundTrip
{
    public static async Task VerifyAsync(object application, string output, bool editNative)
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
        try
        {
            if (editNative)
            {
                dynamic reference = document.InlineShapes.AddOLEObject(ClassType: MathTypeOleBridge.ProgId, DisplayAsIcon: false, Range: document.Range(0, 0));
                object nativeServer = reference.OLEFormat.Object;
                try { MathTypeNativeServer.WriteMathMl(nativeServer, "<math xmlns='http://www.w3.org/1998/Math/MathML'><mtext>端</mtext></math>"); }
                finally { Marshal.ReleaseComObject(nativeServer); }
                byte[] referenceNative = MathTypeWordPackage.ReadNative(Convert.ToString(reference.Range.WordOpenXML)!);
                File.WriteAllBytes(Path.Combine(Path.GetDirectoryName(output)!, "mathtype-reference-chinese.bin"), referenceNative);
                Console.WriteLine("REFERENCE|" + MathTypeNativeEquation.ReadMathMl(referenceNative));
                reference.Delete();
            }
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
            E2EAssert.Equal(examples.Length, Convert.ToInt32(document.InlineShapes.Count), "MathType conversion changed the equation count");
            for (int i = 0; i < examples.Length; i++) VerifyShape(document.InlineShapes.Item(i + 1), examples[i].Source, examples[i].Element, editNative);
            var dimensions = Enumerable.Range(1, examples.Length).Select(i => (
                Width: Convert.ToSingle(document.InlineShapes.Item(i).Width), Height: Convert.ToSingle(document.InlineShapes.Item(i).Height))).ToArray();
            string path = Path.Combine(Path.GetDirectoryName(output)!, "word-mathtype.docx");
            document.SaveAs2(path, 16);
            document.Close(0);
            document = word.Documents.Open(path);
            E2EAssert.Equal(examples.Length, Convert.ToInt32(document.InlineShapes.Count), "MathType save/reopen changed the equation count");
            for (int i = 0; i < examples.Length; i++)
            {
                VerifyShape(document.InlineShapes.Item(i + 1), examples[i].Source, examples[i].Element, editNative);
                E2EAssert.True(Math.Abs(Convert.ToSingle(document.InlineShapes.Item(i + 1).Width) - dimensions[i].Width) < 0.1, "MathType width changed after save/reopen");
                E2EAssert.True(Math.Abs(Convert.ToSingle(document.InlineShapes.Item(i + 1).Height) - dimensions[i].Height) < 0.1, "MathType height changed after save/reopen");
            }
            document.ExportAsFixedFormat(Path.ChangeExtension(path, ".pdf"), 17);
            // Change native MathType content, then import it through the existing OLE batch command.
            if (editNative)
            {
                string changed = await renderer.ConvertTypographyToMathMlAsync(@"z^2+\text{新}", FormulaDisplayMode.Inline, FormulaTypography.Default, CancellationToken.None);
                document.InlineShapes.Item(1).OLEFormat.Activate();
                object server = document.InlineShapes.Item(1).OLEFormat.Object;
                try { MathTypeNativeServer.WriteMathMl(server, changed); }
                finally { Marshal.ReleaseComObject(server); }
                Console.WriteLine("PASS|MathType native server opened and edited independently generated MTEF");
            }
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
            if (editNative)
            {
                var edited = imported.Single(e => XDocument.Parse(e.Metadata!.Latex).Root!.Value.Contains("新"));
                E2EAssert.True(XDocument.Parse(edited.Metadata!.Latex).Root!.Value.Contains("z"), "Import restored stale content instead of edited MathType content");
            }
            document.SaveAs2(Path.Combine(Path.GetDirectoryName(output)!, "word-mathtype-import.docx"), 16);
            Console.WriteLine("PASS|Word MathType to OLE: current edited content, mixed selection, first failure continues, worker thread");
            Console.WriteLine("PASS|MathType native fraction, Chinese, superscript, root, matrix, integral and styles; Word save/reopen");
            await VerifyLayoutAsync(application, (object)document, output);
        }
        finally { document.Close(0); }
    }

    private static void VerifyShape(dynamic shape, string source, string element, bool nativeRead)
    {
        E2EAssert.Equal(MathTypeOleBridge.ProgId, Convert.ToString(shape.OLEFormat.ProgID), "MathType class identity");
        byte[] native = MathTypeWordPackage.ReadNative(Convert.ToString(shape.Range.WordOpenXML)!);
        string mathMl = MathTypeNativeEquation.ReadMathMl(native);
        string flatOpc = Convert.ToString(shape.Range.WordOpenXML)!;
        var package = XDocument.Parse(flatOpc);
        XNamespace pkg = "http://schemas.microsoft.com/office/2006/xmlPackage";
        var picture = package.Descendants(pkg + "part").Single(p => (string?)p.Attribute(pkg + "contentType") == "image/x-wmf");
        using (var stream = new MemoryStream(Convert.FromBase64String(picture.Element(pkg + "binaryData")!.Value)))
        using (var image = Image.FromStream(stream))
        using (var bitmap = new Bitmap(320, 200))
        {
            using (var graphics = Graphics.FromImage(bitmap)) { graphics.Clear(Color.White); graphics.DrawImage(image, 0, 0, bitmap.Width, bitmap.Height); }
            int ink = 0;
            for (int x = 0; x < bitmap.Width; x++)
                for (int y = 0; y < bitmap.Height; y++)
                    if (bitmap.GetPixel(x, y).ToArgb() != Color.White.ToArgb()) ink++;
            E2EAssert.True(ink > 10, "MathType WMF preview is blank");
        }
        if (nativeRead)
        {
            shape.OLEFormat.Activate();
            object server = shape.OLEFormat.Object;
            try { mathMl = MathTypeNativeServer.ReadAndCloseMathMl(server); }
            finally { Marshal.ReleaseComObject(server); }
        }
        var xml = XDocument.Parse(mathMl);
        Console.WriteLine("MATHTYPE|" + source + "|" + mathMl);
        E2EAssert.True(xml.Descendants().Any(e => e.Name.LocalName == element
            || (element == "msubsup" && e.Name.LocalName == "munderover")), "MathType lost structure " + element);
        if (element == "msubsup") E2EAssert.True(xml.Root!.Value.Contains("∫")
            && xml.Root.Value.Contains("0") && xml.Root.Value.Contains("1"), "MathType lost integral bounds");
        if (source.Contains("端")) E2EAssert.True(xml.Root!.Value.Contains("端"), "MathType lost Chinese text");
        if (!nativeRead && source.Contains("textcolor")) E2EAssert.True(xml.Descendants().Attributes("mathcolor").Any(), "MathType native data lost color");
    }
}
