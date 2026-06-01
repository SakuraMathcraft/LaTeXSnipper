namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class ComConstants
{
    public const int SOk = 0;
    public const int SFalse = 1;
    public const int ENotImpl = unchecked((int)0x80004001);
    public const int ENoInterface = unchecked((int)0x80004002);
    public const int EPointer = unchecked((int)0x80004003);
    public const int EFail = unchecked((int)0x80004005);
    public const int ClassENoAggregation = unchecked((int)0x80040110);
    public const int OleEBlank = unchecked((int)0x80040007);
    public const int DvEDvaspect = unchecked((int)0x8004006B);
    public const int DvETymed = unchecked((int)0x80040069);
    public const int DvEFormatEtc = unchecked((int)0x80040064);

    public const int DvAspectContent = 1;
    public const int TymedEnhmf = 64;
    public const short CfEnhmetafile = 14;
    public const uint OleCloseSaveIfDirty = 0;
    public const uint OleCloseNoSave = 1;
    public const uint OleMiscRecomposeOnResize = 0x1;
    public const uint OleMiscInsideOut = 0x80;
    public const uint OleMiscActivateWhenVisible = 0x100;

    public const uint ClsctxLocalServer = 0x4;
    public const uint RegclsSingleUse = 0x0;
    public const uint RegclsMultipleUse = 0x1;
    public const uint RegclsSuspended = 0x4;
}
