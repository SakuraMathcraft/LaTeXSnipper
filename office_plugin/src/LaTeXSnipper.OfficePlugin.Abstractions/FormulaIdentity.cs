using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>
/// Stable identity for a LaTeXSnipper-managed formula inside an Office document.
/// </summary>
public sealed class FormulaIdentity
{
    public FormulaIdentity(string documentId, string equationId)
    {
        if (string.IsNullOrWhiteSpace(documentId))
        {
            throw new ArgumentException("Document ID is required.", nameof(documentId));
        }

        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        DocumentId = documentId;
        EquationId = equationId;
    }

    public string DocumentId { get; }

    public string EquationId { get; }

    public string ToStorageKey()
    {
        return "latexsnipper:" + DocumentId + ":" + EquationId;
    }
}
