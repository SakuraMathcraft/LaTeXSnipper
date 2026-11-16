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
            throw new ArgumentException("文档标识不能为空。", nameof(documentId));
        }

        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("公式标识不能为空。", nameof(equationId));
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
