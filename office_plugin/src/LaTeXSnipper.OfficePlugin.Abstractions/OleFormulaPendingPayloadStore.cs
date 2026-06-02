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
            ?? throw new InvalidOperationException("Cannot open OLE formula payload registry key.");
        key.SetValue(PendingPayloadValue, OleFormulaPayloadJson.Serialize(metadata, presentation), RegistryValueKind.String);
    }
}
#endif
