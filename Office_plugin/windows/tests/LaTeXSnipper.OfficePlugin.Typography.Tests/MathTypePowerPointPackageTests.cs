using System;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Rendering;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace LaTeXSnipper.OfficePlugin.Typography.Tests;

[TestClass]
public sealed class MathTypePowerPointPackageTests
{
    private static readonly XNamespace P = "http://schemas.openxmlformats.org/presentationml/2006/main";
    private static readonly XNamespace R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private static readonly XNamespace Relations = "http://schemas.openxmlformats.org/package/2006/relationships";

    [TestMethod]
    public void ReadsCurrentNativeContentByLogicalSlideOrderAndShapeIdentity()
    {
        string path = CreatePresentation();
        try
        {
            Assert.AreEqual("selected", Value(MathTypePowerPointPackage.ReadNative(path, 1, 43)));
            Assert.AreEqual("other", Value(MathTypePowerPointPackage.ReadNative(path, 2, 43)));
            Assert.AreEqual(23.5, MathTypeNativeEquation.ReadFontSizePoints(MathTypePowerPointPackage.ReadNative(path, 1, 43)), 0.001);
        }
        finally { File.Delete(path); }
    }

    [TestMethod]
    public void ChoiceAndFallbackCanReferenceTheSameNativeObject()
    {
        string path = CreatePresentation(duplicateObject: true);
        try { Assert.AreEqual("selected", Value(MathTypePowerPointPackage.ReadNative(path, 1, 43))); }
        finally { File.Delete(path); }
    }

    [TestMethod]
    [DataRow("External", "oleObject", "Equation.DSMT4")]
    [DataRow("", "image", "Equation.DSMT4")]
    [DataRow("", "oleObject", "Excel.Sheet.12")]
    public void RejectsLinkedOrMismatchedObjects(string targetMode, string relationType, string progId)
    {
        string path = CreatePresentation(targetMode, relationType, progId);
        try { Assert.ThrowsExactly<InvalidDataException>(() => MathTypePowerPointPackage.ReadNative(path, 1, 43)); }
        finally { File.Delete(path); }
    }

    private static string Value(byte[] native) => XDocument.Parse(MathTypeNativeEquation.ReadMathMl(native)).Root!.Value;

    private static string CreatePresentation(string targetMode = "", string relationType = "oleObject",
        string progId = "Equation.DSMT4", bool duplicateObject = false)
    {
        string path = Path.Combine(Path.GetTempPath(), "latexsnipper-ppt-package-test-" + Guid.NewGuid().ToString("N") + ".pptx");
        using var zip = ZipFile.Open(path, ZipArchiveMode.Create);
        WriteXml(zip, "ppt/presentation.xml", new XElement(P + "presentation", new XElement(P + "sldIdLst",
            new XElement(P + "sldId", new XAttribute(R + "id", "first")),
            new XElement(P + "sldId", new XAttribute(R + "id", "second")))));
        WriteXml(zip, "ppt/_rels/presentation.xml.rels", new XElement(Relations + "Relationships",
            Relationship("first", "slide", "slides/slide7.xml"), Relationship("second", "slide", "slides/slide3.xml")));
        var nativeObject = new XElement(P + "oleObj", new XAttribute("progId", progId),
            new XAttribute(R + "id", "currentNative"), new XElement(P + "embed"));
        var frame = new XElement(P + "graphicFrame", new XElement(P + "nvGraphicFramePr",
            new XElement(P + "cNvPr", new XAttribute("id", 43))), nativeObject);
        if (duplicateObject)
        {
            XNamespace mc = "http://schemas.openxmlformats.org/markup-compatibility/2006";
            nativeObject.Remove();
            frame.Add(new XElement(mc + "AlternateContent", new XElement(mc + "Choice", nativeObject),
                new XElement(mc + "Fallback", new XElement(nativeObject))));
        }
        WriteXml(zip, "ppt/slides/slide7.xml", new XElement(P + "sld", frame));
        WriteXml(zip, "ppt/slides/_rels/slide7.xml.rels", new XElement(Relations + "Relationships",
            Relationship("currentNative", relationType, "../embeddings/selected.bin", targetMode)));
        WriteXml(zip, "ppt/slides/slide3.xml", new XElement(P + "sld", new XElement(frame)));
        WriteXml(zip, "ppt/slides/_rels/slide3.xml.rels", new XElement(Relations + "Relationships",
            Relationship("currentNative", "oleObject", "../embeddings/other.bin")));
        Write(zip, "ppt/embeddings/selected.bin", Native("selected"));
        Write(zip, "ppt/embeddings/other.bin", Native("other"));
        return path;
    }

    private static byte[] Native(string value) => MathTypeCompoundFile.Create(MathTypeNativeEquation.Create(
        "<math><mi>" + value + "</mi></math>", 23.5));

    private static XElement Relationship(string id, string type, string target, string targetMode = "")
        => new XElement(Relations + "Relationship", new XAttribute("Id", id), new XAttribute("Type", R.NamespaceName + "/" + type),
            new XAttribute("Target", target), targetMode.Length == 0 ? null : new XAttribute("TargetMode", targetMode));

    private static void WriteXml(ZipArchive zip, string name, XElement element)
        => Write(zip, name, Encoding.UTF8.GetBytes(element.ToString(SaveOptions.DisableFormatting)));

    private static void Write(ZipArchive zip, string name, byte[] bytes)
    {
        using var stream = zip.CreateEntry(name).Open();
        stream.Write(bytes, 0, bytes.Length);
    }
}
