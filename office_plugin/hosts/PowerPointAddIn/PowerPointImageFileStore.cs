using System;
using System.Globalization;
using System.IO;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointImageFileStore
{
    private const float MaxFormulaWidthPoints = 420f;
    private static readonly TimeSpan TemporaryFileLifetime = TimeSpan.FromDays(7);
    private readonly string _directory;

    public PowerPointImageFileStore(string? directory = null)
    {
        _directory = string.IsNullOrWhiteSpace(directory)
            ? Path.Combine(Path.GetTempPath(), "LaTeXSnipper", "OfficePlugin", "PowerPoint")
            : directory!;
    }

    public PowerPointRenderedImage SavePng(byte[] png, double widthPoints, double heightPoints)
    {
        if (png == null || png.Length == 0)
        {
            throw new ArgumentException("PNG data is required.", nameof(png));
        }

        Directory.CreateDirectory(_directory);
        CleanupExpiredFiles();
        string fileName = "formula-"
            + DateTime.UtcNow.ToString("yyyyMMddHHmmssfff", CultureInfo.InvariantCulture)
            + "-"
            + Guid.NewGuid().ToString("N")
            + ".png";
        string path = Path.Combine(_directory, fileName);
        File.WriteAllBytes(path, png);

        float width = (float)widthPoints;
        float height = (float)heightPoints;
        if (width > MaxFormulaWidthPoints)
        {
            float scale = MaxFormulaWidthPoints / width;
            width *= scale;
            height *= scale;
        }

        return new PowerPointRenderedImage(path, width, height);
    }

    private void CleanupExpiredFiles()
    {
        if (!Directory.Exists(_directory))
        {
            return;
        }

        DateTime threshold = DateTime.UtcNow - TemporaryFileLifetime;
        foreach (string file in Directory.GetFiles(_directory, "*.png"))
        {
            try
            {
                if (File.GetLastWriteTimeUtc(file) < threshold)
                {
                    File.Delete(file);
                }
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
        }
    }
}
