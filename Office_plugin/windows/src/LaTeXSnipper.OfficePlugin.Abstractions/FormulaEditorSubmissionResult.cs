namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class FormulaEditorSubmissionResult
{
    private FormulaEditorSubmissionResult(bool success, string message)
    {
        Success = success;
        Message = message;
    }

    public bool Success { get; }

    public string Message { get; }

    public static FormulaEditorSubmissionResult Accepted()
    {
        return new FormulaEditorSubmissionResult(true, string.Empty);
    }

    public static FormulaEditorSubmissionResult Rejected(string message)
    {
        return new FormulaEditorSubmissionResult(false, message ?? string.Empty);
    }
}
