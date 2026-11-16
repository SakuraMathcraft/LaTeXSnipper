using System;
using System.IO;
using System.Reflection;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class MathJaxAssetResolver
{
    private const string MathJaxRootName = "MathJax";
    private const string MathJaxBundleRelativePath = "startup.js";

    private readonly string? _explicitRoot;

    public MathJaxAssetResolver(string? explicitRoot = null)
    {
        _explicitRoot = explicitRoot;
    }

    public string ResolveStartupScript()
    {
        string root = ResolveRoot();
        string bundle = Path.Combine(root, MathJaxBundleRelativePath);
        if (!File.Exists(bundle))
        {
            throw new FileNotFoundException("MathJax TeX/MathML SVG bundle was not found.", bundle);
        }

        return bundle;
    }

    public string Version
    {
        get
        {
            string json = File.ReadAllText(Path.Combine(ResolveRoot(), "resources.json"));
#if NET48
            var data = new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<System.Collections.Generic.Dictionary<string, object>>(json);
            return (string)data["version"];
#else
            using var document = System.Text.Json.JsonDocument.Parse(json);
            return document.RootElement.GetProperty("version").GetString()!;
#endif
        }
    }

    /// <summary>Uses the packaged renderer configuration as the single symbol-font catalog.</summary>
    public System.Collections.Generic.IReadOnlyList<string> SymbolFonts
    {
        get
        {
            string config = File.ReadAllText(Path.Combine(ResolveRoot(), "config.js"));
            int start = config.IndexOf('{');
            int end = config.LastIndexOf('}');
            if (start < 0 || end <= start) throw new FormatException("Invalid MathJax font configuration.");
            string json = config.Substring(start, end - start + 1);
            var fonts = new System.Collections.Generic.List<string>();
#if NET48
            var data = new System.Web.Script.Serialization.JavaScriptSerializer()
                .Deserialize<System.Collections.Generic.Dictionary<string, object>>(json);
            foreach (object font in (System.Collections.IEnumerable)data["fonts"])
                fonts.Add((string)font);
#else
            using var document = System.Text.Json.JsonDocument.Parse(json);
            foreach (var font in document.RootElement.GetProperty("fonts").EnumerateArray())
                fonts.Add(font.GetString()!);
#endif
            if (fonts.Count == 0) throw new FormatException("MathJax font catalog is empty.");
            return fonts.AsReadOnly();
        }
    }

    public string ResolveRoot()
    {
        foreach (string candidate in GetCandidateRoots())
        {
            if (File.Exists(Path.Combine(candidate, MathJaxBundleRelativePath)))
            {
                return candidate;
            }
        }

        throw new DirectoryNotFoundException("MathJax assets were not found.");
    }

    private string[] GetCandidateRoots()
    {
        string assemblyDirectory = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location) ?? AppDomain.CurrentDomain.BaseDirectory;
        string baseDirectory = AppDomain.CurrentDomain.BaseDirectory;

        if (_explicitRoot is string explicitRoot && !string.IsNullOrWhiteSpace(explicitRoot))
        {
            return new[]
            {
                explicitRoot,
                Path.Combine(explicitRoot, MathJaxRootName),
                Path.Combine(assemblyDirectory, MathJaxRootName),
                Path.Combine(baseDirectory, MathJaxRootName),
                Path.GetFullPath(Path.Combine(assemblyDirectory, "..", MathJaxRootName)),
                Path.GetFullPath(Path.Combine(baseDirectory, "..", MathJaxRootName))
            };
        }

        return new[]
        {
            Path.Combine(assemblyDirectory, MathJaxRootName),
            Path.Combine(baseDirectory, MathJaxRootName),
            Path.GetFullPath(Path.Combine(assemblyDirectory, "..", MathJaxRootName)),
            Path.GetFullPath(Path.Combine(baseDirectory, "..", MathJaxRootName)),
            Path.GetFullPath(Path.Combine(assemblyDirectory, "..\\..\\..\\..\\src\\assets", MathJaxRootName)),
            Path.GetFullPath(Path.Combine(baseDirectory, "..\\..\\..\\..\\src\\assets", MathJaxRootName))
        };
    }
}
