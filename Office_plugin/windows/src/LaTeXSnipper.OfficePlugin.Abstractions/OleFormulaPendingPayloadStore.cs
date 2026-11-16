#if NET48
using System;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public static class OleFormulaPendingPayloadStore
{
    private const string KeyPath = @"Software\LaTeXSnipper\OfficePlugin\OleFormulaObject";
    private const string PendingPayloadValue = "PendingPayload";

    public static void SavePendingPayload(FormulaMetadata metadata, OlePresentationResult presentation)
    {
        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        using RegistryKey key = Registry.CurrentUser.CreateSubKey(KeyPath)
            ?? throw new InvalidOperationException("无法打开 OLE 公式数据注册表项。");
        key.SetValue(PendingPayloadValue, OleFormulaPayloadJson.Serialize(metadata, presentation), RegistryValueKind.String);
    }
}
#endif
