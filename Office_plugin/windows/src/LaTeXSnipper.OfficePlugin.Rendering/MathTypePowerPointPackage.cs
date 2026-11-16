using System;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Embeds native MathType content and its preview in a single-slide PowerPoint package.</summary>
public static class MathTypePowerPointPackage
{
    private static readonly XNamespace P = "http://schemas.openxmlformats.org/presentationml/2006/main";
    private static readonly XNamespace A = "http://schemas.openxmlformats.org/drawingml/2006/main";
    private static readonly XNamespace R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private static readonly XNamespace Relationships = "http://schemas.openxmlformats.org/package/2006/relationships";
    private static readonly XNamespace ContentTypes = "http://schemas.openxmlformats.org/package/2006/content-types";
    private const int MaxPartBytes = 64 * 1024 * 1024;

    public static byte[] Create(byte[] template, byte[] compoundFile, OlePresentationResult presentation,
        float left, float top, float width, float height, float rotation, float slideWidth, float slideHeight)
    {
        if (!(width > 0) || !(height > 0) || !(slideWidth > 0) || !(slideHeight > 0)
            || new[] { left, top, width, height, rotation, slideWidth, slideHeight }.Any(v => float.IsInfinity(v) || float.IsNaN(v)))
            throw new InvalidDataException("Invalid PowerPoint MathType geometry.");
        _ = MathTypeNativeEquation.ReadMathMl(MathTypeCompoundFile.ReadNative(compoundFile));
        byte[] preview = MathTypeWmfPreview.Create(presentation.Payload, (float)presentation.WidthPoints, (float)presentation.HeightPoints);
        using var buffer = new MemoryStream();
        buffer.Write(template, 0, template.Length);
        buffer.Position = 0;
        using (var zip = new ZipArchive(buffer, ZipArchiveMode.Update, leaveOpen: true))
        {
            var main = ReadXml(zip, "ppt/presentation.xml");
            var slides = main.Descendants(P + "sldId").ToArray();
            if (slides.Length != 1) throw new InvalidDataException("MathType insertion requires a single-slide template.");
            var size = main.Root!.Element(P + "sldSz") ?? throw new InvalidDataException("PowerPoint slide dimensions are missing.");
            size.SetAttributeValue("cx", Emu(slideWidth));
            size.SetAttributeValue("cy", Emu(slideHeight));
            size.Attribute("type")?.Remove();
            string slidePart = Resolve(zip, "ppt/presentation.xml", (string)slides[0].Attribute(R + "id")!, "slide");
            var slide = ReadXml(zip, slidePart);
            var tree = slide.Descendants(P + "spTree").Single();
            if (tree.Elements().Any(e => e.Name != P + "nvGrpSpPr" && e.Name != P + "grpSpPr"))
                throw new InvalidDataException("MathType insertion template must have an empty slide.");
            var picture = new XElement(P + "pic",
                new XElement(P + "nvPicPr", new XElement(P + "cNvPr", new XAttribute("id", 0), new XAttribute("name", "")),
                    new XElement(P + "cNvPicPr"), new XElement(P + "nvPr")),
                new XElement(P + "blipFill", new XElement(A + "blip", new XAttribute(R + "embed", "formulaPreview")),
                    new XElement(A + "stretch", new XElement(A + "fillRect"))),
                new XElement(P + "spPr", Transform(A + "xfrm", left, top, width, height, rotation),
                    new XElement(A + "prstGeom", new XAttribute("prst", "rect"), new XElement(A + "avLst"))));
            tree.Add(new XElement(P + "graphicFrame",
                new XElement(P + "nvGraphicFramePr",
                    new XElement(P + "cNvPr", new XAttribute("id", 2), new XAttribute("name", "MathType Equation")),
                    new XElement(P + "cNvGraphicFramePr", new XElement(A + "graphicFrameLocks", new XAttribute("noChangeAspect", 1))),
                    new XElement(P + "nvPr")),
                Transform(P + "xfrm", left, top, width, height, rotation),
                new XElement(A + "graphic", new XElement(A + "graphicData", new XAttribute("uri", "http://schemas.openxmlformats.org/presentationml/2006/ole"),
                    new XElement(P + "oleObj", new XAttribute("name", "Equation"), new XAttribute("progId", "Equation.DSMT4"),
                        new XAttribute(R + "id", "formulaNative"), new XAttribute("imgW", Emu(presentation.WidthPoints)),
                        new XAttribute("imgH", Emu(presentation.HeightPoints)), new XElement(P + "embed"), picture)))));
            var relations = ReadXml(zip, RelationshipPart(slidePart));
            relations.Root!.Add(Relationship("formulaNative", "oleObject", "../embeddings/formula.bin"),
                Relationship("formulaPreview", "image", "../media/formula.wmf"));
            var types = ReadXml(zip, "[Content_Types].xml");
            types.Root!.Add(new XElement(ContentTypes + "Override", new XAttribute("PartName", "/ppt/embeddings/formula.bin"),
                new XAttribute("ContentType", "application/vnd.openxmlformats-officedocument.oleObject")));
            if (!types.Root.Elements(ContentTypes + "Default").Any(e => (string?)e.Attribute("Extension") == "wmf"))
                types.Root.Add(new XElement(ContentTypes + "Default", new XAttribute("Extension", "wmf"), new XAttribute("ContentType", "image/x-wmf")));
            WriteXml(zip, slidePart, slide);
            WriteXml(zip, "ppt/presentation.xml", main);
            WriteXml(zip, RelationshipPart(slidePart), relations);
            WriteXml(zip, "[Content_Types].xml", types);
            WritePart(zip, "ppt/embeddings/formula.bin", compoundFile);
            WritePart(zip, "ppt/media/formula.wmf", preview);
        }
        return buffer.ToArray();
    }

    public static byte[] ReadNative(string presentationPath, int slideIndex, int shapeId)
    {
        using var file = File.OpenRead(presentationPath);
        using var zip = new ZipArchive(file, ZipArchiveMode.Read);
        var slides = ReadXml(zip, "ppt/presentation.xml").Descendants(P + "sldId").ToArray();
        if (slideIndex < 1 || slideIndex > slides.Length) throw new InvalidDataException("MathType slide is missing.");
        string slidePart = Resolve(zip, "ppt/presentation.xml", (string)slides[slideIndex - 1].Attribute(R + "id")!, "slide");
        var frame = ReadXml(zip, slidePart).Descendants(P + "graphicFrame").SingleOrDefault(e =>
            (string?)e.Element(P + "nvGraphicFramePr")?.Element(P + "cNvPr")?.Attribute("id") == shapeId.ToString(CultureInfo.InvariantCulture))
            ?? throw new InvalidDataException("MathType shape is missing from the presentation.");
        var objects = frame.Descendants(P + "oleObj").ToArray();
        if (objects.Length == 0 || objects.Any(e => !string.Equals((string?)e.Attribute("progId"), "Equation.DSMT4", StringComparison.OrdinalIgnoreCase)
            || e.Element(P + "embed") == null))
            throw new InvalidDataException("Expected an embedded native MathType equation.");
        var ids = objects.Select(e => (string?)e.Attribute(R + "id")).Distinct().ToArray();
        if (ids.Length != 1 || string.IsNullOrEmpty(ids[0])) throw new InvalidDataException("MathType relationship is missing or ambiguous.");
        string id = ids[0]!;
        string nativePart = Resolve(zip, slidePart, id, "oleObject");
        return MathTypeCompoundFile.ReadNative(ReadPart(zip, nativePart));
    }

    private static long Emu(double points) => checked((long)Math.Round(points * 12700d));

    private static XElement Transform(XName name, float left, float top, float width, float height, float rotation)
        => new XElement(name, name == A + "xfrm" ? new XAttribute("rot", Math.Round(rotation * 60000d)) : null,
            new XElement(A + "off", new XAttribute("x", Emu(left)), new XAttribute("y", Emu(top))),
            new XElement(A + "ext", new XAttribute("cx", Emu(width)), new XAttribute("cy", Emu(height))));

    private static string RelationshipPart(string part)
    {
        int split = part.LastIndexOf('/') + 1;
        return part.Substring(0, split) + "_rels/" + part.Substring(split) + ".rels";
    }

    private static XElement Relationship(string id, string type, string target) => new XElement(Relationships + "Relationship",
        new XAttribute("Id", id), new XAttribute("Type", R.NamespaceName + "/" + type), new XAttribute("Target", target));

    private static string Resolve(ZipArchive zip, string part, string id, string type)
    {
        var relation = ReadXml(zip, RelationshipPart(part)).Descendants(Relationships + "Relationship")
            .SingleOrDefault(e => (string?)e.Attribute("Id") == id)
            ?? throw new InvalidDataException("Missing PowerPoint relationship: " + id);
        if ((string?)relation.Attribute("Type") != R.NamespaceName + "/" + type || (string?)relation.Attribute("TargetMode") == "External")
            throw new InvalidDataException("Unexpected external or mismatched PowerPoint relationship.");
        var target = new Uri(new Uri("http://package/" + part), (string)relation.Attribute("Target")!);
        if (target.Host != "package" || target.Query.Length != 0 || target.Fragment.Length != 0)
            throw new InvalidDataException("Invalid embedded PowerPoint part path.");
        return target.AbsolutePath.TrimStart('/');
    }

    private static XDocument ReadXml(ZipArchive zip, string part) => XDocument.Parse(Encoding.UTF8.GetString(ReadPart(zip, part)));

    private static byte[] ReadPart(ZipArchive zip, string part)
    {
        var entry = zip.GetEntry(part) ?? throw new InvalidDataException("Missing PowerPoint part: " + part);
        if (entry.Length > MaxPartBytes) throw new InvalidDataException("PowerPoint part exceeds the formula size limit.");
        using var stream = entry.Open();
        using var buffer = new MemoryStream();
        stream.CopyTo(buffer);
        return buffer.ToArray();
    }

    private static void WriteXml(ZipArchive zip, string part, XDocument document)
        => WritePart(zip, part, Encoding.UTF8.GetBytes(document.ToString(SaveOptions.DisableFormatting)));

    private static void WritePart(ZipArchive zip, string part, byte[] bytes)
    {
        zip.GetEntry(part)?.Delete();
        using var stream = zip.CreateEntry(part, CompressionLevel.Optimal).Open();
        stream.Write(bytes, 0, bytes.Length);
    }
}
