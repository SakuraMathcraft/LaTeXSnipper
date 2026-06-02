using System;
using System.Collections.Generic;
using System.Globalization;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class OlePayloadRegistryStore
{
    private const string KeyPath = @"Software\LaTeXSnipper\OfficePlugin\OleFormulaObject";
    private const string EditorPayloadValue = "EditorPayload";
    private const string EditorPayloadResultValue = "EditorPayloadResult";

    public static string ReadEditorPayload()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(KeyPath, writable: false);
        return key?.GetValue(EditorPayloadValue) as string ?? string.Empty;
    }

    public static void SaveEditorPayloadResult(string payloadJson)
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(KeyPath)
            ?? throw new InvalidOperationException("Cannot open OLE formula payload registry key.");
        key.SetValue(EditorPayloadResultValue, payloadJson, RegistryValueKind.String);
    }

    public static string ReadLatex(string payloadJson)
    {
        if (string.IsNullOrWhiteSpace(payloadJson))
        {
            return string.Empty;
        }

        var serializer = new JavaScriptSerializer();
        var root = serializer.Deserialize<Dictionary<string, object>>(payloadJson);
        return root.TryGetValue("latex", out object value) ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }

    public static string WithPresentation(string payloadJson, string latex, string rendererVersion, OlePresentationResult presentation)
    {
        if (presentation == null)
        {
            throw new ArgumentNullException(nameof(presentation));
        }

        var serializer = new JavaScriptSerializer();
        Dictionary<string, object> root = string.IsNullOrWhiteSpace(payloadJson)
            ? new Dictionary<string, object>()
            : serializer.Deserialize<Dictionary<string, object>>(payloadJson);
        root["latex"] = latex;
        root["renderEngine"] = RenderEngineKind.MathJaxSvg.ToString();
        root["rendererVersion"] = rendererVersion;
        root["widthPoints"] = presentation.WidthPoints.ToString(CultureInfo.InvariantCulture);
        root["heightPoints"] = presentation.HeightPoints.ToString(CultureInfo.InvariantCulture);
        root["baselinePoints"] = presentation.BaselinePoints.ToString(CultureInfo.InvariantCulture);
        root["presentationKind"] = presentation.PresentationKind.ToString();
        root["presentationMimeType"] = presentation.MimeType;
        root["presentationPayloadBase64"] = Convert.ToBase64String(presentation.Payload);
        return serializer.Serialize(root);
    }
}
