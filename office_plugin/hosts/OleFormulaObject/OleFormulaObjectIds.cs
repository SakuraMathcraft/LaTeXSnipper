using System;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class OleFormulaObjectIds
{
    public const string ProgId = "LaTeXSnipper.Formula";

    public const string VersionedProgId = "LaTeXSnipper.Formula.1";

    public const string FriendlyName = "LaTeXSnipper Formula";

    public const string ClassIdString = "B7F5B4AB-5F94-4D87-A29F-9A41D41B3B9F";

    public static readonly Guid ClassId = new Guid(ClassIdString);
}
