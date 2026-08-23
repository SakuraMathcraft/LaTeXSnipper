using System;
using System.Collections;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Automation;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointAutomationRecognitionParser
{
    public static string ParseScreenshotOcrResponse(string responseJson)
    {
        if (string.IsNullOrWhiteSpace(responseJson))
        {
            throw new InvalidOperationException(AutomationApiUserMessages.InvalidResponse);
        }

        var root = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(responseJson);
        var job = AsDictionary(Required(root, "job"), "识别任务");
        if (!string.Equals(Text(job, "state"), "completed", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(ErrorMessage(job));
        }

        if (!(Required(job, "items") is IEnumerable items))
        {
            throw new InvalidOperationException(AutomationApiUserMessages.InvalidResponse);
        }

        foreach (object value in items)
        {
            string text = Text(AsDictionary(value, "识别结果"), "text");
            if (!string.IsNullOrWhiteSpace(text))
            {
                return text;
            }
        }

        throw new InvalidOperationException("未识别到公式内容，请在桌面端重新识别后再试。");
    }

    private static string ErrorMessage(Dictionary<string, object> job)
    {
        if (job.TryGetValue("error", out object value))
        {
            var error = AsDictionary(value, "识别错误");
            return AutomationApiUserMessages.ForErrorCode(Text(error, "code"));
        }

        return AutomationApiUserMessages.RecognitionFailed;
    }

    private static Dictionary<string, object> AsDictionary(object value, string label)
    {
        return value as Dictionary<string, object>
            ?? throw new InvalidOperationException(label + "数据格式无效。");
    }

    private static object Required(Dictionary<string, object> dictionary, string key)
    {
        return dictionary.TryGetValue(key, out object value)
            ? value
            : throw new InvalidOperationException(AutomationApiUserMessages.InvalidResponse);
    }

    private static string Text(Dictionary<string, object> dictionary, string key)
    {
        return dictionary.TryGetValue(key, out object value) ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }
}
