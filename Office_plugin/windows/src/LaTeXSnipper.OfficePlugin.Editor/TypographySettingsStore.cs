#if NET48
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Editor;

/// <summary>Current global typography defaults for each Office host and portable JSON import/export.</summary>
public sealed class TypographySettingsStore
{
    private const int Schema = 2;
    private const int MaximumFileBytes = 64 * 1024;
    private const string MutexName = @"Local\LaTeXSnipper.OfficePlugin.TypographySettings";
    private readonly string _root;
    private readonly JavaScriptSerializer _json = new JavaScriptSerializer();

    public TypographySettingsStore(string? root = null)
    {
        _root = root ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "LaTeXSnipper", "OfficePlugin");
    }

    public FormulaTypographyDefaults Load(string host)
    {
        ValidateHost(host);
        return WithLock(() => ReadSettings()[host]);
    }

    public void Save(string host, FormulaTypography typography, bool followHostFontSize)
    {
        ValidateHost(host);
        ValidateTypography(typography);
        WithLock(() =>
        {
            var settings = ReadSettings();
            settings[host] = new FormulaTypographyDefaults(typography, followHostFontSize);
            AtomicWrite(SettingsPath, SerializeSettings(settings));
            return 0;
        });
    }

    public string Import(string host, string file, IReadOnlyList<string> symbolFonts)
    {
        ValidateHost(host);
        FormulaTypographyDefaults imported = ReadDefaults(ReadJson(file));
        if (symbolFonts == null || !symbolFonts.Contains(imported.Typography.SymbolFontId))
            throw new FormatException("预设使用未打包的数学符号字体：" + imported.Typography.SymbolFontId);
        Save(host, imported.Typography, imported.FollowHostFontSize);
        return Path.GetFileNameWithoutExtension(file);
    }

    public void Export(string host, string file)
    {
        FormulaTypographyDefaults defaults = Load(host);
        AtomicWrite(file, _json.Serialize(WriteDefaults(defaults)));
    }

    private string SettingsPath => Path.Combine(_root, "settings.json");

    private Dictionary<string, FormulaTypographyDefaults> ReadSettings()
    {
        if (!File.Exists(SettingsPath)) return DefaultSettings();
        try
        {
            var data = ReadJson(SettingsPath);
            if (data.TryGetValue("schema", out object version) && version is int schema && schema == Schema
                && data.TryGetValue("word", out object word) && word is Dictionary<string, object> wordFields
                && data.TryGetValue("powerpoint", out object powerpoint) && powerpoint is Dictionary<string, object> powerpointFields)
                return new Dictionary<string, FormulaTypographyDefaults>
                {
                    ["word"] = ReadDefaults(wordFields),
                    ["powerpoint"] = ReadDefaults(powerpointFields),
                };
        }
        catch (FormatException) { }
        catch (ArgumentException) { }
        File.Delete(SettingsPath);
        var defaults = DefaultSettings();
        AtomicWrite(SettingsPath, SerializeSettings(defaults));
        return defaults;
    }

    private static Dictionary<string, FormulaTypographyDefaults> DefaultSettings() =>
        new Dictionary<string, FormulaTypographyDefaults>
        {
            ["word"] = new FormulaTypographyDefaults(FormulaTypography.Default, false),
            ["powerpoint"] = new FormulaTypographyDefaults(FormulaTypography.Default, false),
        };

    private string SerializeSettings(Dictionary<string, FormulaTypographyDefaults> settings) => _json.Serialize(
        new Dictionary<string, object>
        {
            ["schema"] = Schema,
            ["word"] = WriteDefaults(settings["word"]),
            ["powerpoint"] = WriteDefaults(settings["powerpoint"]),
        });

    private static Dictionary<string, object> WriteDefaults(FormulaTypographyDefaults defaults) => new Dictionary<string, object>
    {
        ["schema"] = Schema,
        ["followHostFontSize"] = defaults.FollowHostFontSize,
        ["typography"] = FormulaTypographyFields.Write(defaults.Typography),
    };

    private static FormulaTypographyDefaults ReadDefaults(Dictionary<string, object> data)
    {
        if (!data.TryGetValue("schema", out object version) || version is not int schema || schema != Schema)
            throw new FormatException("不支持的用户配置版本。");
        if (!data.TryGetValue("followHostFontSize", out object follow) || follow is not bool followHost)
            throw new FormatException("无效的预设字号模式。");
        if (!data.TryGetValue("typography", out object raw) || raw is not Dictionary<string, object> fields)
            throw new FormatException("预设缺少字体样式。");
        FormulaTypography typography = FormulaTypographyFields.Read(fields);
        ValidateTypography(typography);
        return new FormulaTypographyDefaults(typography, followHost);
    }

    private Dictionary<string, object> ReadJson(string file)
    {
        if (!File.Exists(file)) throw new FileNotFoundException("预设文件不存在。", file);
        if (new FileInfo(file).Length > MaximumFileBytes) throw new FormatException("预设文件过大：" + file);
        try { return _json.Deserialize<Dictionary<string, object>>(File.ReadAllText(file))
            ?? throw new FormatException("无效的 JSON：" + file); }
        catch (ArgumentException error) { throw new FormatException("无效的 JSON：" + file, error); }
    }

    private static void ValidateTypography(FormulaTypography typography)
    {
        if (typography == null) throw new ArgumentNullException(nameof(typography));
        foreach (string? family in new[] { typography.NumberFontFamily, typography.CjkFontFamily })
            if (family != null && (family.Length > 128 || family.IndexOfAny(new[] { '<', '>', ';', ':', '/', '\\' }) >= 0
                || family.IndexOf("url(", StringComparison.OrdinalIgnoreCase) >= 0
                || family.IndexOf("@import", StringComparison.OrdinalIgnoreCase) >= 0))
                throw new FormatException("预设包含无效的字体家族描述。");
    }

    private static void ValidateHost(string host)
    {
        if (host != "word" && host != "powerpoint") throw new ArgumentException("未知 Office 宿主。", nameof(host));
    }

    private static void AtomicWrite(string path, string contents)
    {
        string directory = Path.GetDirectoryName(path) ?? throw new ArgumentException("缺少目录。", nameof(path));
        Directory.CreateDirectory(directory);
        string temporary = Path.Combine(directory, "." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            File.WriteAllText(temporary, contents);
            if (File.Exists(path)) File.Replace(temporary, path, path + ".bak");
            else File.Move(temporary, path);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private static T WithLock<T>(Func<T> action)
    {
        using var mutex = new Mutex(false, MutexName);
        bool acquired = false;
        try
        {
            try { acquired = mutex.WaitOne(TimeSpan.FromSeconds(10)); }
            catch (AbandonedMutexException) { acquired = true; }
            if (!acquired) throw new IOException("等待用户配置写入锁超时。");
            return action();
        }
        finally { if (acquired) mutex.ReleaseMutex(); }
    }
}
#endif
