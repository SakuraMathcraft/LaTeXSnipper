#if NET48
using System.Collections.Generic;
using System.Drawing;

namespace LaTeXSnipper.OfficePlugin.Editor;

public sealed class MathLiveFormulaEditorOptions
{
    public MathLiveFormulaEditorOptions(
        string editorHostName,
        string webViewUserDataFolderName,
        IEnumerable<string> devAssetRelativePaths,
        IEnumerable<string> registryPaths)
    {
        EditorHostName = editorHostName;
        WebViewUserDataFolderName = webViewUserDataFolderName;
        DevAssetRelativePaths = new List<string>(devAssetRelativePaths);
        RegistryPaths = new List<string>(registryPaths);
    }

    public string EditorHostName { get; }

    public string WebViewUserDataFolderName { get; }

    public IReadOnlyList<string> DevAssetRelativePaths { get; }

    public IReadOnlyList<string> RegistryPaths { get; }

    public Icon? Icon { get; set; }

    public bool ForceDisplayMode { get; set; }
}
#endif
