using System;
using System.Collections;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Automation;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public static class AutomationRecognitionParser
{
    public static string ParseScreenshotOcrResponse(string responseJson)
    {
        if (string.IsNullOrWhiteSpace(responseJson))
        {
            throw new InvalidOperationException(AutomationApiUserMessages.InvalidResponse);
        }

        var envelope = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(responseJson);
        var job = AsDictionary(GetRequired(envelope, "job"), "识别任务");
        string state = GetString(job, "state");
        if (!string.Equals(state, "completed", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(ReadError(job));
        }

        object itemsValue = GetRequired(job, "items");
        if (!(itemsValue is IEnumerable items))
        {
            throw new InvalidOperationException(AutomationApiUserMessages.InvalidResponse);
        }

        foreach (object itemValue in items)
        {
            var item = AsDictionary(itemValue, "识别结果");
            string text = GetString(item, "text");
            if (!string.IsNullOrWhiteSpace(text))
            {
                return text;
            }
        }

        throw new InvalidOperationException("未识别到公式内容，请在桌面端重新识别后再试。");
    }

    private static string ReadError(Dictionary<string, object> value)
    {
        if (value.TryGetValue("error", out object raw))
        {
            var error = AsDictionary(raw, "识别错误");
            return AutomationApiUserMessages.ForErrorCode(GetString(error, "code"));
        }

        return AutomationApiUserMessages.RecognitionFailed;
    }

    private static Dictionary<string, object> AsDictionary(object value, string label)
    {
        return value as Dictionary<string, object>
            ?? throw new InvalidOperationException(label + "数据格式无效。");
    }

    private static object GetRequired(Dictionary<string, object> dictionary, string key)
    {
        return dictionary.TryGetValue(key, out object value)
            ? value
            : throw new InvalidOperationException(AutomationApiUserMessages.InvalidResponse);
    }

    private static string GetString(Dictionary<string, object> dictionary, string key)
    {
        return dictionary.TryGetValue(key, out object value) ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }
}
