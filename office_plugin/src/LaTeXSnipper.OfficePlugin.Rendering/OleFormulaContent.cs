#if NETFRAMEWORK
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Authoritative content of the embedded object, independent of host identity.</summary>
public sealed class OleFormulaContent
{
    public const string ProgId = "LaTeXSnipper.Formula.1";
    private readonly Dictionary<string, object> fields;
    private static JavaScriptSerializer Serializer() => new() { MaxJsonLength = 32 * 1024 * 1024 };

    private OleFormulaContent(Dictionary<string, object> fields)
    {
        this.fields = fields;
        if (Text("schemaVersion") != FormulaMetadata.CurrentSchemaVersion.ToString(CultureInfo.InvariantCulture))
            throw new FormatException("不支持的 OLE 公式协议版本。");
        _ = Metadata(new FormulaIdentity("validation", "validation"));
        if (!Positive(WidthPoints) || !Positive(HeightPoints)) throw new FormatException("OLE 公式自然尺寸无效。");
    }

    public static bool IsFormula(object shapeObject)
    {
        dynamic shape = shapeObject;
        try
        {
            string id = Convert.ToString(shape.OLEFormat.ProgID) ?? "";
            return string.Equals(id, ProgId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(id, "LaTeXSnipper.Formula", StringComparison.OrdinalIgnoreCase);
        }
        catch (COMException) { return false; }
    }

    public static OleFormulaContent Read(object shapeObject)
    {
        dynamic shape = shapeObject;
        object server = shape.OLEFormat.Object;
        try
        {
            string json = ((dynamic)server).GetPayload();
            return new OleFormulaContent(Serializer().Deserialize<Dictionary<string, object>>(json));
        }
        finally { if (Marshal.IsComObject(server)) Marshal.ReleaseComObject(server); }
    }

    public double WidthPoints => Number("widthPoints");
    public double HeightPoints => Number("heightPoints");
    public FormulaMetadata Metadata(FormulaIdentity identity) => new(identity, Text("latex"),
        Parse<FormulaDisplayMode>("displayMode"), Parse<NumberingMode>("numberingMode"), Text("numberText"),
        RenderEngineKind.MathJaxSvg, FormulaMetadata.CurrentSchemaVersion, FormulaTypographyFields.Read(fields));

    public static void UpdateNumbering(object shapeObject, FormulaMetadata metadata)
    {
        var content = Read(shapeObject);
        var existing = content.Metadata(metadata.Identity);
        if (existing.Latex != metadata.Latex || !existing.Typography.Equals(metadata.Typography)
            || existing.DisplayMode != metadata.DisplayMode)
            throw new InvalidOperationException("公式内容或样式修改必须重新渲染后保存。");
        var presentation = new OlePresentationResult(content.Parse<OlePresentationKind>("presentationKind"),
            content.Text("presentationMimeType"), Convert.FromBase64String(content.Text("presentationPayloadBase64")),
            content.WidthPoints, content.HeightPoints, content.Number("baselinePoints"), content.Text("rendererVersion"));
        dynamic shape = shapeObject;
        object server = shape.OLEFormat.Object;
        try { ((dynamic)server).UpdatePayload(OleFormulaPayloadJson.Serialize(metadata, presentation)); }
        finally { if (Marshal.IsComObject(server)) Marshal.ReleaseComObject(server); }
    }

    private string Text(string key) => fields.TryGetValue(key, out var value)
        ? Convert.ToString(value, CultureInfo.InvariantCulture) ?? ""
        : throw new FormatException("缺少 OLE 公式字段：" + key);
    private double Number(string key) => double.Parse(Text(key), CultureInfo.InvariantCulture);
    private static bool Positive(double value) => value > 0 && !double.IsInfinity(value) && !double.IsNaN(value);
    private T Parse<T>(string key) where T : struct => Enum.TryParse<T>(Text(key), out var value)
        && Enum.IsDefined(typeof(T), value) ? value : throw new FormatException("无效的 OLE 公式字段：" + key);
}
#endif
