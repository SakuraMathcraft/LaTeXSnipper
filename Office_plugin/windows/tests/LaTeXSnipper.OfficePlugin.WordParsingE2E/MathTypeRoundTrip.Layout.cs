using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static partial class MathTypeRoundTrip
{
    private static async Task VerifyLayoutAsync(object application, object sourceDocument, string output)
    {
        dynamic word = application;
        dynamic? document = word.Documents.Add();
        dynamic? copiedDocument = null;
        var adapter = new DynamicWordApplicationAdapter(application);
        var status = new RecordingStatusSink();
        using var controller = WordAddInFactory.CreateController(application, statusSink: status, applicationAdapter: adapter,
            mathJaxHostName: "MathTypeLayout-" + Guid.NewGuid().ToString("N"));
        try
        {
            document.Content.Text = "before after\r";
            const string source = @"e^{i\pi}+1=0";
            dynamic sourceRange = ((dynamic)sourceDocument).InlineShapes.Item(2).Range;
            for (int i = 0; i < 2; i++)
            {
                sourceRange.Copy();
                document.Range(7 + i, 7 + i).Paste();
                document.InlineShapes.Item(i + 1).Range.Select();
                _ = await adapter.LoadSelectedFormulaTargetAsync(CancellationToken.None);
            }
            dynamic table = document.Tables.Add(document.Range(Convert.ToInt32(document.Content.End) - 1), 1, 1);
            table.Cell(1, 1).Range.Text = "table-before table-after";
            int start = Convert.ToInt32(table.Cell(1, 1).Range.Start) + 13;
            for (int i = 0; i < 5; i++)
            {
                sourceRange.Copy();
                document.Range(start + i, start + i).PasteSpecial(DataType: 0, Placement: 0);
                document.InlineShapes.Item(i + 3).Range.Select();
                _ = await adapter.LoadSelectedFormulaTargetAsync(CancellationToken.None);
            }
            string text = Convert.ToString(document.Content.Text);
            int paragraphs = Convert.ToInt32(document.Paragraphs.Count);
            float untouchedWidth = Convert.ToSingle(document.InlineShapes.Item(1).Width);
            dynamic selected = document.InlineShapes.Item(2);
            selected.LockAspectRatio = -1;
            selected.Height = Convert.ToSingle(selected.Height) * 1.5f;
            float width = Convert.ToSingle(selected.Width), height = Convert.ToSingle(selected.Height);
            selected.Range.Select();
            await controller.ConvertSelectedToMathTypeAsync(CancellationToken.None);
            E2EAssert.Equal(7, Convert.ToInt32(document.InlineShapes.Count), "Converting one of two identical objects changed count");
            E2EAssert.Equal(6, (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Count, "Converting one formula also converted its twin");
            E2EAssert.True(Math.Abs(Convert.ToSingle(document.InlineShapes.Item(1).Width) - untouchedWidth) < 0.1, "Unselected twin changed size");
            E2EAssert.True(Math.Abs(Convert.ToSingle(document.InlineShapes.Item(2).Width) - width) < 0.1
                && Math.Abs(Convert.ToSingle(document.InlineShapes.Item(2).Height) - height) < 0.1, "User scaling was lost");
            using (var cancellation = new CancellationTokenSource())
            {
                status.CancelAfterNextBatch(cancellation);
                document.Content.Select();
                bool cancelled = false;
                try { await controller.ConvertSelectedToMathTypeAsync(cancellation.Token); }
                catch (OperationCanceledException) { cancelled = true; }
                E2EAssert.True(cancelled, "MathType batch cancellation was not propagated");
            }
            E2EAssert.Equal(1, (await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None)).Count, "Cancellation modified unprocessed targets");
            E2EAssert.Equal(7, Convert.ToInt32(document.InlineShapes.Count), "Cancellation left extra objects");
            document.Content.Select();
            await controller.ConvertSelectedToMathTypeAsync(CancellationToken.None);
            E2EAssert.Equal(text, Convert.ToString(document.Content.Text), "MathType conversion changed surrounding body/table text");
            E2EAssert.Equal(paragraphs, Convert.ToInt32(document.Paragraphs.Count), "MathType conversion added paragraphs");
            E2EAssert.Equal(1, Convert.ToInt32(document.Tables.Count), "MathType conversion changed table structure");
            document.SaveAs2(Path.Combine(Path.GetDirectoryName(output)!, "word-mathtype-layout.docx"), 16);
            copiedDocument = word.Documents.Add();
            document.InlineShapes.Item(2).Range.Copy();
            copiedDocument.Range(0, 0).Paste();
            document.Close(0);
            document = null;
            VerifyShape(copiedDocument.InlineShapes.Item(1), source, "msup", false);
            E2EAssert.True(Math.Abs(Convert.ToSingle(copiedDocument.InlineShapes.Item(1).Width) - width) < 0.1, "Cross-document copy changed width");
            Console.WriteLine("PASS|MathType identical twins, scaling, adjacent objects, table/body text, cancellation/retry, copy after source closed");
        }
        finally
        {
            if (document != null) document.Close(0);
            if (copiedDocument != null) copiedDocument.Close(0);
        }
    }

}
