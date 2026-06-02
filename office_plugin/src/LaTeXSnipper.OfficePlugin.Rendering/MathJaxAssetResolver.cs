using System;
using System.IO;
using System.Reflection;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class MathJaxAssetResolver
{
    private const string MathJaxRootName = "MathJax-3.2.2";
    private const string MathJaxBundleRelativePath = "es5\\tex-mml-svg.js";

    private readonly string? _explicitRoot;

    public MathJaxAssetResolver(string? explicitRoot = null)
    {
        _explicitRoot = explicitRoot;
    }

    public string ResolveTexSvgBundle()
    {
        string root = ResolveRoot();
        string bundle = Path.Combine(root, MathJaxBundleRelativePath);
        if (!File.Exists(bundle))
        {
            throw new FileNotFoundException("MathJax TeX/MathML SVG bundle was not found.", bundle);
        }

        return bundle;
    }

    public string ResolveRoot()
    {
        foreach (string candidate in GetCandidateRoots())
        {
            if (Directory.Exists(candidate))
            {
                return candidate;
            }
        }

        throw new DirectoryNotFoundException("MathJax 3.2.2 assets were not found.");
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
