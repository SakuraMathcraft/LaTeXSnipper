using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Word Flat OPC containing a native MathType equation and a vector preview.</summary>
public static class MathTypeWordPackage
{
    private static readonly XNamespace P = "http://schemas.microsoft.com/office/2006/xmlPackage";
    private static readonly XNamespace W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
    private static readonly XNamespace R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private static readonly XNamespace Rel = "http://schemas.openxmlformats.org/package/2006/relationships";
    private static readonly XNamespace V = "urn:schemas-microsoft-com:vml";
    private static readonly XNamespace O = "urn:schemas-microsoft-com:office:office";

    public static string Create(byte[] compoundFile, OlePresentationResult presentation, float widthPoints, float heightPoints)
    {
        if (!(widthPoints > 0) || !(heightPoints > 0) || float.IsInfinity(widthPoints) || float.IsInfinity(heightPoints))
            throw new InvalidDataException("Invalid MathType display dimensions.");
        byte[] preview = MathTypeWmfPreview.Create(presentation.Payload, widthPoints, heightPoints);
        string shapeId = "_x0000_i" + unchecked((uint)Guid.NewGuid().GetHashCode()).ToString(CultureInfo.InvariantCulture);
        var shapeType = new XElement(
            V + "shapetype",
            new XAttribute("id", "_x0000_t75"),
            new XAttribute("coordsize", "21600,21600"),
            new XAttribute(O + "spt", "75"),
            new XAttribute(O + "preferrelative", "t"),
            new XAttribute("path", "m@4@5l@4@11@9@11@9@5xe"),
            new XAttribute("filled", "f"),
            new XAttribute("stroked", "f"),
            new XElement(V + "stroke", new XAttribute("joinstyle", "miter")),
            new XElement(
                V + "formulas",
                new XElement(V + "f", new XAttribute("eqn", "if lineDrawn pixelLineWidth 0")),
                new XElement(V + "f", new XAttribute("eqn", "sum @0 1 0")),
                new XElement(V + "f", new XAttribute("eqn", "sum 0 0 @1")),
                new XElement(V + "f", new XAttribute("eqn", "prod @2 1 2")),
                new XElement(V + "f", new XAttribute("eqn", "prod @3 21600 pixelWidth")),
                new XElement(V + "f", new XAttribute("eqn", "prod @3 21600 pixelHeight")),
                new XElement(V + "f", new XAttribute("eqn", "sum @0 0 1")),
                new XElement(V + "f", new XAttribute("eqn", "prod @6 1 2")),
                new XElement(V + "f", new XAttribute("eqn", "prod @7 21600 pixelWidth")),
                new XElement(V + "f", new XAttribute("eqn", "sum @8 21600 0")),
                new XElement(V + "f", new XAttribute("eqn", "prod @7 21600 pixelHeight")),
                new XElement(V + "f", new XAttribute("eqn", "sum @10 21600 0"))),
            new XElement(
                V + "path",
                new XAttribute(O + "extrusionok", "f"),
                new XAttribute("gradientshapeok", "t"),
                new XAttribute(O + "connecttype", "rect")),
            new XElement(
                O + "lock",
                new XAttribute(V + "ext", "edit"),
                new XAttribute("aspectratio", "t")));
        var equation = new XElement(W + "object",
            new XAttribute(W + "dxaOrig", Math.Round(widthPoints * 20)),
            new XAttribute(W + "dyaOrig", Math.Round(heightPoints * 20)),
            shapeType,
            new XElement(V + "shape", new XAttribute("id", shapeId), new XAttribute("type", "#_x0000_t75"),
                new XAttribute("style", string.Format(CultureInfo.InvariantCulture, "width:{0:0.###}pt;height:{1:0.###}pt", widthPoints, heightPoints)),
                new XAttribute(O + "ole", ""),
                new XElement(V + "imagedata", new XAttribute(R + "id", "preview"), new XAttribute(O + "title", ""))),
            new XElement(O + "OLEObject", new XAttribute("Type", "Embed"), new XAttribute("ProgID", "Equation.DSMT4"),
                new XAttribute("ShapeID", shapeId), new XAttribute("DrawAspect", "Content"), new XAttribute("ObjectID", "_" + Guid.NewGuid().ToString("N")),
                new XAttribute(R + "id", "equation")));
        var document = new XElement(W + "document", new XAttribute(XNamespace.Xmlns + "w", W),
            new XAttribute(XNamespace.Xmlns + "r", R), new XAttribute(XNamespace.Xmlns + "v", V), new XAttribute(XNamespace.Xmlns + "o", O),
            new XElement(W + "body", new XElement(W + "p", new XElement(W + "r", equation))));
        return new XDocument(new XElement(P + "package", new XAttribute(XNamespace.Xmlns + "pkg", P),
            XmlPart("/_rels/.rels", "application/vnd.openxmlformats-package.relationships+xml",
                new XElement(Rel + "Relationships", Relationship("document", "officeDocument", "word/document.xml"))),
            XmlPart("/word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml", document),
            XmlPart("/word/_rels/document.xml.rels", "application/vnd.openxmlformats-package.relationships+xml",
                new XElement(Rel + "Relationships", Relationship("preview", "image", "media/equation.wmf"),
                    Relationship("equation", "oleObject", "embeddings/equation.bin"))),
            BinaryPart("/word/media/equation.wmf", "image/x-wmf", preview),
            BinaryPart("/word/embeddings/equation.bin", "application/vnd.openxmlformats-officedocument.oleObject", compoundFile)))
            .ToString(SaveOptions.DisableFormatting);
    }

    public static byte[] ReadNative(string flatOpc)
    {
        if (flatOpc == null || flatOpc.Length > 192 * 1024 * 1024) throw new InvalidDataException("Invalid MathType Flat OPC size.");
        var package = XDocument.Parse(flatOpc);
        var equation = package.Descendants(O + "OLEObject").Single();
        if ((string?)equation.Attribute("ProgID") != "Equation.DSMT4") throw new InvalidDataException("Expected a native MathType object.");
        string id = (string?)equation.Attribute(R + "id") ?? throw new InvalidDataException("Missing MathType relationship.");
        var documentPart = equation.Ancestors(P + "part").Single();
        string partName = (string)documentPart.Attribute(P + "name")!;
        var partUri = new Uri("http://package" + partName);
        string relName = partName.Substring(0, partName.LastIndexOf('/') + 1) + "_rels/" + partName.Substring(partName.LastIndexOf('/') + 1) + ".rels";
        var relPart = package.Descendants(P + "part").Single(p => (string?)p.Attribute(P + "name") == relName);
        var relationship = relPart.Descendants(Rel + "Relationship").Single(r => (string?)r.Attribute("Id") == id);
        if ((string?)relationship.Attribute("TargetMode") == "External") throw new InvalidDataException("MathType object must be embedded.");
        string target = new Uri(partUri, (string)relationship.Attribute("Target")!).AbsolutePath;
        var binary = package.Descendants(P + "part").Single(p => (string?)p.Attribute(P + "name") == target).Element(P + "binaryData")
            ?? throw new InvalidDataException("Missing MathType binary data.");
        return MathTypeCompoundFile.ReadNative(Convert.FromBase64String(binary.Value));
    }

    private static XElement Relationship(string id, string type, string target) => new XElement(Rel + "Relationship",
        new XAttribute("Id", id), new XAttribute("Type", R.NamespaceName + "/" + type), new XAttribute("Target", target));

    private static XElement XmlPart(string name, string type, XElement content) => new XElement(P + "part",
        new XAttribute(P + "name", name), new XAttribute(P + "contentType", type), new XElement(P + "xmlData", content));

    private static XElement BinaryPart(string name, string type, byte[] content) => new XElement(P + "part",
        new XAttribute(P + "name", name), new XAttribute(P + "contentType", type), new XAttribute(P + "compression", "store"),
        new XElement(P + "binaryData", Convert.ToBase64String(content)));
}
