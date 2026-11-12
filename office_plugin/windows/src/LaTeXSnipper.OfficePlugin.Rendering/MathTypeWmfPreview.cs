using System;
using System.IO;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class MathTypeWmfPreview
{
    private const uint AldusPlaceableKey = 0x9AC6CDD7;
    private const ushort PlaceableInch = 2304;
    private const int MmAnisotropic = 8;
    internal static byte[] Create(byte[] emf, float widthPt, float heightPt)
    {
        string path = Path.Combine(Path.GetTempPath(), "latexsnipper-preview-" + Guid.NewGuid().ToString("N") + ".emf");
        try
        {
            File.WriteAllBytes(path, emf);
            return EnsureMathTypePlaceableWmfWindowRecords(ConvertEnhancedMetafileToPlaceableWmf(path, widthPt, heightPt));
        }
        finally { File.Delete(path); }
    }

    private static byte[] ConvertEnhancedMetafileToPlaceableWmf(
        string emfPath,
        float widthPt,
        float heightPt)
    {
        if (string.IsNullOrWhiteSpace(emfPath) || !File.Exists(emfPath))
            throw new FileNotFoundException("EMF preview is unavailable.", emfPath);
        if (!(widthPt > 0) || !(heightPt > 0))
            throw new InvalidDataException(
                $"Invalid WMF preview size {widthPt}x{heightPt} pt.");

        var enhancedMetafile = GetEnhMetaFileW(emfPath);
        if (enhancedMetafile == IntPtr.Zero)
            throw new InvalidDataException($"Windows could not open EMF preview '{emfPath}'.");
        var referenceDc = GetDC(IntPtr.Zero);
        try
        {
            var rawLength = GetWinMetaFileBits(
                enhancedMetafile,
                0,
                null,
                MmAnisotropic,
                referenceDc);
            if (rawLength == 0 || rawLength > 64 * 1024 * 1024)
                throw new InvalidDataException(
                    $"Windows could not convert the EMF preview to WMF; size={rawLength}.");
            var rawWmf = new byte[rawLength];
            var written = GetWinMetaFileBits(
                enhancedMetafile,
                rawLength,
                rawWmf,
                MmAnisotropic,
                referenceDc);
            if (written != rawLength)
                throw new InvalidDataException(
                    $"Windows returned an incomplete WMF preview: {written}/{rawLength} bytes.");

            // Genuine MathType WMFs use whole-point picture bounds (the same
            // dimensions later written to Word's dxaOrig/dyaOrig).  Preserve the
            // visual VML size separately, but make the embedded WMF's original
            // coordinate extent match MathType's native object format.
            var originalWidthPt = widthPt;
            var originalHeightPt = heightPt;
            var right = checked((short)Math.Max(
                1,
                Math.Min(short.MaxValue, (int)Math.Round(originalWidthPt * PlaceableInch / 72d))));
            var bottom = checked((short)Math.Max(
                1,
                Math.Min(short.MaxValue, (int)Math.Round(originalHeightPt * PlaceableInch / 72d))));
            var placeable = BuildPlaceableHeader(right, bottom);
            var result = new byte[placeable.Length + rawWmf.Length];
            Buffer.BlockCopy(placeable, 0, result, 0, placeable.Length);
            Buffer.BlockCopy(rawWmf, 0, result, placeable.Length, rawWmf.Length);
            return result;
        }
        finally
        {
            if (referenceDc != IntPtr.Zero) ReleaseDC(IntPtr.Zero, referenceDc);
            DeleteEnhMetaFile(enhancedMetafile);
        }
    }


    private static byte[] BuildPlaceableHeader(short right, short bottom)
    {
        var bytes = new byte[22];
        WriteUInt32(bytes, 0, AldusPlaceableKey);
        WriteUInt16(bytes, 4, 0);
        WriteInt16(bytes, 6, 0);
        WriteInt16(bytes, 8, 0);
        WriteInt16(bytes, 10, right);
        WriteInt16(bytes, 12, bottom);
        WriteUInt16(bytes, 14, PlaceableInch);
        WriteUInt32(bytes, 16, 0);
        ushort checksum = 0;
        for (var offset = 0; offset < 20; offset += 2)
            checksum ^= BitConverter.ToUInt16(bytes, offset);
        WriteUInt16(bytes, 20, checksum);
        return bytes;
    }


    private static void WriteUInt16(byte[] bytes, int offset, ushort value)
    {
        var encoded = BitConverter.GetBytes(value);
        Buffer.BlockCopy(encoded, 0, bytes, offset, encoded.Length);
    }


    private static void WriteInt16(byte[] bytes, int offset, short value) =>
        WriteUInt16(bytes, offset, unchecked((ushort)value));


    private static void WriteUInt32(byte[] bytes, int offset, uint value)
    {
        var encoded = BitConverter.GetBytes(value);
        Buffer.BlockCopy(encoded, 0, bytes, offset, encoded.Length);
    }


    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetEnhMetaFileW(string fileName);


    [DllImport("gdi32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeleteEnhMetaFile(IntPtr enhancedMetafile);


    [DllImport("gdi32.dll")]
    private static extern uint GetWinMetaFileBits(
        IntPtr enhancedMetafile,
        uint bufferSize,
        [Out] byte[]? data,
        int mapMode,
        IntPtr referenceDc);


    [DllImport("user32.dll")]
    private static extern IntPtr GetDC(IntPtr window);


    [DllImport("user32.dll")]
    private static extern int ReleaseDC(IntPtr window, IntPtr dc);


    private static byte[] EnsureMathTypePlaceableWmfWindowRecords(byte[] previewWmf)
    {
        const uint aldusPlaceableKey = 0x9ac6cdd7;
        const ushort metaSetWindowOrg = 0x020b;
        const ushort metaSetWindowExt = 0x020c;
        const int firstRecordOffset = 40;
        if (previewWmf is null
            || previewWmf.Length < firstRecordOffset + 6
            || BitConverter.ToUInt32(previewWmf, 0) != aldusPlaceableKey)
            throw new InvalidDataException("MathType preview is not a valid placeable WMF.");

        var declaredWords = BitConverter.ToUInt32(previewWmf, 28);
        if (declaredWords > int.MaxValue / 2
            || checked((int)declaredWords * 2) != previewWmf.Length - 22)
            throw new InvalidDataException("MathType WMF header length does not match its payload.");

        var hasWindowOrigin = false;
        var hasWindowExtent = false;
        var insertionOffset = firstRecordOffset;
        var leadingSetup = true;
        for (var offset = firstRecordOffset; offset + 6 <= previewWmf.Length;)
        {
            var words = BitConverter.ToUInt32(previewWmf, offset);
            if (words < 3 || words > int.MaxValue / 2)
                throw new InvalidDataException("MathType WMF contains an invalid record length.");
            var size = checked((int)words * 2);
            if (offset + size > previewWmf.Length)
                throw new InvalidDataException("MathType WMF contains a truncated record.");
            var function = BitConverter.ToUInt16(previewWmf, offset + 4);
            hasWindowOrigin |= function == metaSetWindowOrg;
            hasWindowExtent |= function == metaSetWindowExt;
            if (leadingSetup
                && function is 0x0102 or 0x0201 or 0x012e)
                insertionOffset = offset + size;
            else
                leadingSetup = false;
            offset += size;
            if (function == 0) break;
        }

        if (hasWindowOrigin && hasWindowExtent) return previewWmf;
        if (hasWindowOrigin || hasWindowExtent)
            throw new InvalidDataException(
                "MathType WMF contains only one of SETWINDOWORG/SETWINDOWEXT.");

        var left = BitConverter.ToInt16(previewWmf, 6);
        var top = BitConverter.ToInt16(previewWmf, 8);
        var right = BitConverter.ToInt16(previewWmf, 10);
        var bottom = BitConverter.ToInt16(previewWmf, 12);
        var width = checked((short)(right - left));
        var height = checked((short)(bottom - top));
        if (width <= 0 || height <= 0)
            throw new InvalidDataException("MathType placeable WMF has invalid logical bounds.");

        var result = new byte[checked(previewWmf.Length + 20)];
        Buffer.BlockCopy(previewWmf, 0, result, 0, insertionOffset);
        WriteWmfRecord(result, insertionOffset, metaSetWindowOrg, top, left);
        WriteWmfRecord(result, insertionOffset + 10, metaSetWindowExt, height, width);
        Buffer.BlockCopy(
            previewWmf,
            insertionOffset,
            result,
            insertionOffset + 20,
            previewWmf.Length - insertionOffset);
        WriteUInt32(result, 28, checked(declaredWords + 10));
        return result;
    }


    private static void WriteWmfRecord(
        byte[] target,
        int offset,
        ushort function,
        short firstParameter,
        short secondParameter)
    {
        WriteUInt32(target, offset, 5);
        WriteUInt16(target, offset + 4, function);
        WriteUInt16(target, offset + 6, unchecked((ushort)firstParameter));
        WriteUInt16(target, offset + 8, unchecked((ushort)secondParameter));
    }

}