using System;
using System.Collections.Generic;
using System.IO;

#if NET48
using System.Web.Script.Serialization;
#else
using System.Text.Json;
#endif

namespace LaTeXSnipper.OfficePlugin.Automation;

internal sealed class AutomationApiConfiguration
{
    public string BaseUrl { get; private set; } = string.Empty;

    public string Token { get; private set; } = string.Empty;

    public static AutomationApiConfiguration Read(string path)
    {
        if (!File.Exists(path))
        {
            throw new InvalidOperationException(AutomationApiUserMessages.DesktopUnavailable);
        }

        string json = File.ReadAllText(path);
#if NET48
        var values = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(json);
        return new AutomationApiConfiguration
        {
            BaseUrl = values.TryGetValue("base_url", out object baseUrl) ? Convert.ToString(baseUrl) ?? string.Empty : string.Empty,
            Token = values.TryGetValue("token", out object token) ? Convert.ToString(token) ?? string.Empty : string.Empty,
        };
#else
        using JsonDocument document = JsonDocument.Parse(json);
        JsonElement root = document.RootElement;
        return new AutomationApiConfiguration
        {
            BaseUrl = root.TryGetProperty("base_url", out JsonElement baseUrl) ? baseUrl.GetString() ?? string.Empty : string.Empty,
            Token = root.TryGetProperty("token", out JsonElement token) ? token.GetString() ?? string.Empty : string.Empty,
        };
#endif
    }
}
