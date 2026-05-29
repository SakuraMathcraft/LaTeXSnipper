using System;
using System.Collections.Generic;

#if NET48
using System.Web.Script.Serialization;
#else
using System.Text.Json;
#endif

namespace LaTeXSnipper.OfficePlugin.Bridge;

internal sealed class BridgeConfiguration
{
    public string BridgeUrl { get; private set; } = string.Empty;

    public string Token { get; private set; } = string.Empty;

    public static BridgeConfiguration FromJson(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            throw new InvalidOperationException("Bridge config response was empty.");
        }

#if NET48
        var serializer = new JavaScriptSerializer();
        var envelope = serializer.Deserialize<Dictionary<string, object>>(json);
        if (!envelope.TryGetValue("result", out object resultObject)
            || resultObject is not Dictionary<string, object> result)
        {
            throw new InvalidOperationException("Bridge config response did not contain a result object.");
        }

        return new BridgeConfiguration
        {
            BridgeUrl = result.TryGetValue("bridge_url", out object bridgeUrl) ? Convert.ToString(bridgeUrl) ?? string.Empty : string.Empty,
            Token = result.TryGetValue("token", out object token) ? Convert.ToString(token) ?? string.Empty : string.Empty,
        };
#else
        using JsonDocument document = JsonDocument.Parse(json);
        if (!document.RootElement.TryGetProperty("result", out JsonElement result))
        {
            throw new InvalidOperationException("Bridge config response did not contain a result object.");
        }

        return new BridgeConfiguration
        {
            BridgeUrl = result.TryGetProperty("bridge_url", out JsonElement bridgeUrl) ? bridgeUrl.GetString() ?? string.Empty : string.Empty,
            Token = result.TryGetProperty("token", out JsonElement token) ? token.GetString() ?? string.Empty : string.Empty,
        };
#endif
    }
}
