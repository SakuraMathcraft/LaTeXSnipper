using System;
using System.Collections.Generic;
using System.Globalization;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class OleFormulaPayloadSerializer
{
    public static string Serialize(OleFormulaPayload payload)
    {
        if (payload == null)
        {
            throw new ArgumentNullException(nameof(payload));
        }

        var dto = new Dictionary<string, object>
        {
            ["schemaVersion"] = payload.SchemaVersion,
            ["documentId"] = payload.Identity.DocumentId,
            ["equationId"] = payload.Identity.EquationId,
            ["latex"] = payload.Latex,
            ["displayMode"] = payload.DisplayMode.ToString(),
            ["numberingMode"] = payload.NumberingMode.ToString(),
            ["numberText"] = payload.NumberText,
            ["renderEngine"] = payload.RenderEngine.ToString(),
            ["rendererVersion"] = payload.RendererVersion,
            ["widthPoints"] = payload.WidthPoints,
            ["heightPoints"] = payload.HeightPoints,
            ["baselinePoints"] = payload.BaselinePoints
        };
        return new JavaScriptSerializer().Serialize(dto);
    }

    public static OleFormulaPayload Deserialize(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            throw new ArgumentException("OLE payload JSON is required.", nameof(json));
        }

        var serializer = new JavaScriptSerializer();
        var root = serializer.Deserialize<Dictionary<string, object>>(json);
        int schemaVersion = GetInt(root, "schemaVersion");
        if (schemaVersion != OleFormulaPayload.CurrentSchemaVersion)
        {
            throw new NotSupportedException("Unsupported OLE formula schema version: " + schemaVersion.ToString(CultureInfo.InvariantCulture));
        }

        var identity = new FormulaIdentity(GetString(root, "documentId"), GetString(root, "equationId"));
        return new OleFormulaPayload(
            identity,
            GetString(root, "latex"),
            ReadEnum(root, "displayMode", FormulaDisplayMode.Display),
            ReadEnum(root, "numberingMode", NumberingMode.None),
            GetString(root, "numberText"),
            GetString(root, "rendererVersion"),
            GetDouble(root, "widthPoints"),
            GetDouble(root, "heightPoints"),
            GetDouble(root, "baselinePoints"));
    }

    private static string GetString(Dictionary<string, object> root, string propertyName)
    {
        return root.TryGetValue(propertyName, out object value) ? Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty : string.Empty;
    }

    private static int GetInt(Dictionary<string, object> root, string propertyName)
    {
        return root.TryGetValue(propertyName, out object value) && int.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Integer, CultureInfo.InvariantCulture, out int result)
            ? result
            : 0;
    }

    private static double GetDouble(Dictionary<string, object> root, string propertyName)
    {
        return root.TryGetValue(propertyName, out object value) && double.TryParse(Convert.ToString(value, CultureInfo.InvariantCulture), NumberStyles.Float, CultureInfo.InvariantCulture, out double result)
            ? result
            : 0;
    }

    private static T ReadEnum<T>(Dictionary<string, object> root, string propertyName, T fallback)
        where T : struct
    {
        string value = GetString(root, propertyName);
        return Enum.TryParse(value, ignoreCase: true, out T parsed) ? parsed : fallback;
    }
}
