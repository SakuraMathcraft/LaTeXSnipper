#if NET48
using System.Collections.Generic;
using System.Drawing;

namespace LaTeXSnipper.OfficePlugin.Editor;

public sealed class MathLiveFormulaEditorOptions
{
    public MathLiveFormulaEditorOptions(
        string editorHostName,
        string sharedEditorHostName,
        string webViewUserDataFolderName,
        IEnumerable<string> devAssetRelativePaths,
        IEnumerable<string> sharedDevAssetRelativePaths,
        IEnumerable<string> registryPaths)
    {
        EditorHostName = editorHostName;
        SharedEditorHostName = sharedEditorHostName;
        WebViewUserDataFolderName = webViewUserDataFolderName;
        DevAssetRelativePaths = new List<string>(devAssetRelativePaths);
        SharedDevAssetRelativePaths = new List<string>(sharedDevAssetRelativePaths);
        RegistryPaths = new List<string>(registryPaths);
    }

    public string EditorHostName { get; }

    public string SharedEditorHostName { get; }

    public string WebViewUserDataFolderName { get; }

    public IReadOnlyList<string> DevAssetRelativePaths { get; }

    public IReadOnlyList<string> SharedDevAssetRelativePaths { get; }

    public IReadOnlyList<string> RegistryPaths { get; }

    public Icon? Icon { get; set; }

    public bool ForceDisplayMode { get; set; }
}
#endif
