using System;
using System.IO;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Editor;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.MetadataSafety.Tests;

[TestClass]
public sealed class TypographySettingsStoreTests
{
    private string _root = string.Empty;

    [TestInitialize]
    public void Start() => _root = Path.Combine(Path.GetTempPath(), "latexsnipper-settings-" + Guid.NewGuid().ToString("N"));

    [TestCleanup]
    public void Finish()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, true);
    }

    [TestMethod]
    public void WordAndPowerPointDefaultsPersistIndependently()
    {
        var store = new TypographySettingsStore(_root);
        var word = new FormulaTypography("mathjax-tex", "Times New Roman", "宋体", FormulaMathStyle.Upright, 10.5, "#123ABC");
        var powerpoint = FormulaTypography.Default.WithFontSize(24);
        Task.WaitAll(Task.Run(() => store.Save("word", word, true)),
            Task.Run(() => new TypographySettingsStore(_root).Save("powerpoint", powerpoint, false)));
        var reopened = new TypographySettingsStore(_root);
        Assert.AreEqual(word, reopened.Load("word").Typography);
        Assert.IsTrue(reopened.Load("word").FollowHostFontSize);
        Assert.AreEqual(powerpoint, reopened.Load("powerpoint").Typography);
        Assert.IsFalse(reopened.Load("powerpoint").FollowHostFontSize);
    }

    [TestMethod]
    public void InvalidSettingsAreDeletedAndRecreatedWithDefaults()
    {
        var store = new TypographySettingsStore(_root);
        store.Save("word", FormulaTypography.Default.WithFontSize(18), true);
        string file = Path.Combine(_root, "settings.json");
        File.WriteAllText(file, "{bad json");
        Assert.AreEqual(FormulaTypography.Default, store.Load("word").Typography);
        Assert.IsFalse(store.Load("word").FollowHostFontSize);
        StringAssert.Contains(File.ReadAllText(file), "\"schema\":2");
    }

    [TestMethod]
    public void JsonExportAndImportApplyToTheSelectedHost()
    {
        var store = new TypographySettingsStore(_root);
        var style = new FormulaTypography("mathjax-tex", "Times New Roman", "宋体", FormulaMathStyle.Bold, 14, "#224466");
        store.Save("word", style, true);
        string file = Path.Combine(_root, "论文公式.json");
        store.Export("word", file);
        Assert.AreEqual("论文公式", store.Import("powerpoint", file, new[] { "mathjax-tex" }));
        Assert.AreEqual(style, store.Load("powerpoint").Typography);
        Assert.IsTrue(store.Load("powerpoint").FollowHostFontSize);
        Assert.ThrowsExactly<FormatException>(() => store.Import("word", file, new[] { "mathjax-stix2" }));
        Assert.AreEqual(style, store.Load("word").Typography);
    }
}
