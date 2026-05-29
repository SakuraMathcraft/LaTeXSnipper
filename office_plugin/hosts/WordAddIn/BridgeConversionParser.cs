using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public static class BridgeConversionParser
{
    public static BridgeConversionResult ParseConvertLatexResponse(string responseJson)
    {
        if (string.IsNullOrWhiteSpace(responseJson))
        {
            throw new InvalidOperationException("Bridge returned an empty conversion response.");
        }

        var serializer = new JavaScriptSerializer();
        object raw = serializer.DeserializeObject(responseJson);
        var envelope = AsDictionary(raw, "Bridge response");

        if (!TryGetBoolean(envelope, "ok", out bool ok))
        {
            throw new InvalidOperationException("Bridge response is missing the ok flag.");
        }

        if (!ok)
        {
            throw new InvalidOperationException(ReadBridgeError(envelope));
        }

        var result = AsDictionary(GetRequired(envelope, "result"), "Bridge conversion result");
        string latex = GetString(result, "latex");
        bool display = !TryGetBoolean(result, "display", out bool parsedDisplay) || parsedDisplay;
        string omml = GetString(result, "omml");
        if (!LooksLikeOmml(omml))
        {
            throw new InvalidOperationException("Bridge conversion result does not contain editable OMML.");
        }

        return new BridgeConversionResult(latex, display, omml, GetStringList(result, "warnings"));
    }

    private static bool LooksLikeOmml(string value)
    {
        return value.IndexOf("<m:oMath", StringComparison.Ordinal) >= 0;
    }

    private static string ReadBridgeError(Dictionary<string, object> envelope)
    {
        if (!envelope.TryGetValue("error", out object? rawError) || rawError == null)
        {
            return "Bridge request failed.";
        }

        var error = AsDictionary(rawError, "Bridge error");
        string message = GetString(error, "message");
        return string.IsNullOrWhiteSpace(message) ? "Bridge request failed." : message;
    }

    private static Dictionary<string, object> AsDictionary(object value, string label)
    {
        if (value is Dictionary<string, object> dictionary)
        {
            return dictionary;
        }

        throw new InvalidOperationException(label + " has an unexpected JSON shape.");
    }

    private static object GetRequired(Dictionary<string, object> dictionary, string key)
    {
        if (!dictionary.TryGetValue(key, out object? value) || value == null)
        {
            throw new InvalidOperationException("Bridge response is missing " + key + ".");
        }

        return value;
    }

    private static string GetString(Dictionary<string, object> dictionary, string key)
    {
        return dictionary.TryGetValue(key, out object? value) && value != null ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }

    private static bool TryGetBoolean(Dictionary<string, object> dictionary, string key, out bool value)
    {
        if (dictionary.TryGetValue(key, out object? raw) && raw is bool boolean)
        {
            value = boolean;
            return true;
        }

        value = false;
        return false;
    }

    private static IReadOnlyList<string> GetStringList(Dictionary<string, object> dictionary, string key)
    {
        if (!dictionary.TryGetValue(key, out object? value) || value is not object[] items)
        {
            return Array.Empty<string>();
        }

        var result = new List<string>();
        foreach (object item in items)
        {
            string text = Convert.ToString(item) ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(text))
            {
                result.Add(text);
            }
        }

        return result;
    }
}
