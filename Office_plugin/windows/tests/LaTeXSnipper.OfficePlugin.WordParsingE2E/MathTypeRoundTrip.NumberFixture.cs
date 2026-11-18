using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static partial class MathTypeRoundTrip
{
    public static async Task VerifyNumberFixtureAsync(object application, string fixture, string output, bool testInstalledMathType)
    {
        string copy = Path.Combine(Path.GetDirectoryName(output)!, "native-number-fixture.docx");
        File.Copy(fixture, copy);
        dynamic word = application;
        dynamic document = word.Documents.Open(copy);
        using var adapter = new DynamicWordApplicationAdapter(application);
        using var controller = WordAddInFactory.CreateController(application, new RecordingStatusSink(), applicationAdapter: adapter,
            mathJaxHostName: "MathTypeNativeNumber-" + Guid.NewGuid().ToString("N"));
        try
        {
            int count = Convert.ToInt32((object)document.InlineShapes.Count);
            E2EAssert.True(count > 0, "Fixture requires native numbered MathType objects");
            string[] references = NativeReferenceTargets((object)document, includeLabel: true);
            E2EAssert.True(references.Length > 0, "Fixture requires at least one MathType reference");
            document.Content.Select();
            await controller.ConvertSelectedToOleAsync(CancellationToken.None);
            var imported = await adapter.LoadFormulaEntriesAsync(true, CancellationToken.None);
            E2EAssert.Equal(count, imported.Count, "Imported native numbered formulas");
            E2EAssert.True(imported.All(entry => entry.Metadata!.NumberingMode == NumberingMode.Automatic), "Native numbering was not adopted");
            E2EAssert.True(((string)document.Content.WordOpenXML).Contains("SEQ LaTeXSnipperEquation"), "LaTeXSnipper sequence not created");
            await controller.RenumberAllAsync(CancellationToken.None);
            E2EAssert.Equal(string.Join("|", references), string.Join("|", NativeReferenceTargets((object)document, includeLabel: true)), "References after import");
            document.Content.Select();
            await controller.ConvertSelectedToMathTypeAsync(CancellationToken.None);
            E2EAssert.Equal(string.Join("|", references), string.Join("|", NativeReferenceTargets((object)document, includeLabel: true)), "References after export");
            for (int index = 1; index <= count; index++)
            {
                dynamic shape = document.InlineShapes.Item(index);
                E2EAssert.Equal("Equation.DSMT4", Convert.ToString((object)shape.OLEFormat.ProgID), "Re-exported native equation");
                E2EAssert.True(((string)shape.Range.Paragraphs.Item(1).Range.WordOpenXML).Contains("MACROBUTTON MTPlaceRef"),
                    "MathType's native number wrapper was not created");
            }
            if (testInstalledMathType)
            {
                foreach (dynamic field in document.Fields)
                    if (Convert.ToString((object)field.Code.Text)!.TrimStart().StartsWith("REF ZEqnNum", StringComparison.OrdinalIgnoreCase))
                        field.Result.Text = "STALE-MATHTYPE-REFERENCE";
                Console.WriteLine("STAGE|Calling installed MathType Update Equation Numbers");
                word.Run("MTCommand_UpdateEqns");
                E2EAssert.Equal(string.Join("|", references),
                    string.Join("|", NativeReferenceTargets((object)document, includeLabel: true, checkResult: true)),
                    "MathType's update command broke an existing reference");
                Console.WriteLine("PASS|Installed MathType update command on converted numbering");
            }
            document.Save();
            Console.WriteLine("PASS|Native MathType numbered Word fixture, LaTeXSnipper numbering and MathType references");
        }
        finally { document.Close(0); }
    }

    private static string[] NativeReferenceTargets(object target, bool includeLabel, bool checkResult = false)
    {
        dynamic document = target;
        var names = new System.Collections.Generic.List<string>();
        foreach (dynamic field in document.Fields)
        {
            string code = Convert.ToString((object)field.Code.Text)!.Trim();
            if (!code.StartsWith("REF ZEqnNum", StringComparison.OrdinalIgnoreCase)) continue;
            string name = code.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries)[1];
            E2EAssert.True(Convert.ToBoolean((object)document.Bookmarks.Exists(name)), "MathType reference bookmark was lost");
            dynamic range = document.Bookmarks.Item(name).Range;
            string label = Convert.ToString((object)range.Text)!;
            E2EAssert.True(!string.IsNullOrWhiteSpace(label), "MathType reference bookmark is empty");
            if (checkResult) E2EAssert.Equal(label, Convert.ToString((object)field.Result.Text), "MathType did not refresh the reference");
            names.Add(includeLabel ? name + "=" + label : name);
        }
        return names.ToArray();
    }
}
