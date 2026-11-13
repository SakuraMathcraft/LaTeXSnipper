using System;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal static class PowerPointDocumentIdentityStore
{
    private const string PropertyName = "LaTeXSnipper.DocumentId";
    private const int MsoPropertyTypeString = 4;

    public static string GetOrCreate(dynamic presentation)
    {
        dynamic properties = presentation.CustomDocumentProperties;
        try
        {
            string existing = Convert.ToString(properties.Item(PropertyName).Value) ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(existing))
            {
                return existing;
            }
        }
        catch
        {
        }

        string documentId = Guid.NewGuid().ToString("N");
        properties.Add(PropertyName, false, MsoPropertyTypeString, documentId);
        return documentId;
    }
}
