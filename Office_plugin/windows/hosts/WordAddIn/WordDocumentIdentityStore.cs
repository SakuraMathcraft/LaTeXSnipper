using System;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordDocumentIdentityStore
{
    private const string VariableName = "LaTeXSnipper.DocumentId";

    public static string GetOrCreate(dynamic document)
    {
        try
        {
            string existing = Convert.ToString(document.Variables.Item(VariableName).Value) ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(existing))
            {
                return existing;
            }
        }
        catch
        {
        }

        string documentId = Guid.NewGuid().ToString("N");
        document.Variables.Add(VariableName, documentId);
        return documentId;
    }
}
