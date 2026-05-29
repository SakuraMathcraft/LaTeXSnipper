using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public static class BridgeRecognitionParser
{
    public static string ParseScreenshotOcrResponse(string responseJson)
    {
        if (string.IsNullOrWhiteSpace(responseJson))
        {
            throw new InvalidOperationException("Bridge returned an empty OCR response.");
        }

        var serializer = new JavaScriptSerializer();
        var envelope = serializer.Deserialize<Dictionary<string, object>>(responseJson);
        if (envelope == null)
        {
            throw new InvalidOperationException("Bridge OCR response was not a JSON object.");
        }

        if (!TryGetBoolean(envelope, "ok", out bool ok))
        {
            throw new InvalidOperationException("Bridge OCR response is missing the ok flag.");
        }

        if (!ok)
        {
            throw new InvalidOperationException(ReadBridgeError(envelope));
        }

        Dictionary<string, object> result = AsDictionary(GetRequired(envelope, "result"), "Bridge OCR result");
        string latex = GetString(result, "latex");
        if (string.IsNullOrWhiteSpace(latex))
        {
            throw new InvalidOperationException("Bridge OCR result did not contain LaTeX.");
        }

        return latex;
    }

    private static string ReadBridgeError(Dictionary<string, object> envelope)
    {
        if (!envelope.TryGetValue("error", out object rawError))
        {
            return "Bridge OCR request failed.";
        }

        var error = AsDictionary(rawError, "Bridge OCR error");
        string message = GetString(error, "message");
        return string.IsNullOrWhiteSpace(message) ? "Bridge OCR request failed." : message;
    }

    private static Dictionary<string, object> AsDictionary(object value, string label)
    {
        if (value is Dictionary<string, object> dictionary)
        {
            return dictionary;
        }

        throw new InvalidOperationException(label + " was not a JSON object.");
    }

    private static object GetRequired(Dictionary<string, object> dictionary, string key)
    {
        if (!dictionary.TryGetValue(key, out object value))
        {
            throw new InvalidOperationException("Bridge OCR response is missing " + key + ".");
        }

        return value;
    }

    private static string GetString(Dictionary<string, object> dictionary, string key)
    {
        return dictionary.TryGetValue(key, out object value) ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }

    private static bool TryGetBoolean(Dictionary<string, object> dictionary, string key, out bool value)
    {
        value = false;
        if (!dictionary.TryGetValue(key, out object raw))
        {
            return false;
        }

        if (raw is bool boolValue)
        {
            value = boolValue;
            return true;
        }

        return bool.TryParse(Convert.ToString(raw), out value);
    }
}
