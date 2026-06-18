param(
    [switch]$SkipWord,
    [switch]$SkipPowerPoint
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$abstractionsPath = Join-Path $repoRoot "office_plugin\src\LaTeXSnipper.OfficePlugin.Abstractions\bin\Release\net48\LaTeXSnipper.OfficePlugin.Abstractions.dll"
$wordAddInPath = Join-Path $repoRoot "office_plugin\hosts\WordAddIn\bin\Release\net48\LaTeXSnipper.OfficePlugin.WordAddIn.dll"
$powerPointAddInPath = Join-Path $repoRoot "office_plugin\hosts\PowerPointAddIn\bin\Release\net48\LaTeXSnipper.OfficePlugin.PowerPointAddIn.dll"

foreach ($assemblyPath in @($abstractionsPath, $wordAddInPath, $powerPointAddInPath)) {
    if (-not (Test-Path -LiteralPath $assemblyPath)) {
        throw "Missing assembly: $assemblyPath. Build the Office plugin in Release mode first."
    }
}

$abstractionsAssembly = [Reflection.Assembly]::LoadFrom($abstractionsPath)
$wordAssembly = [Reflection.Assembly]::LoadFrom($wordAddInPath)
$powerPointAssembly = [Reflection.Assembly]::LoadFrom($powerPointAddInPath)

function New-FormulaMetadata {
    param(
        [string]$DocumentId,
        [string]$EquationId,
        [string]$Latex,
        [string]$DisplayMode,
        [string]$NumberingMode,
        [string]$NumberText,
        [string]$RenderEngine,
        [string]$FontColor,
        [string]$FontStyle,
        [double]$FontScale
    )

    $identityType = $abstractionsAssembly.GetType("LaTeXSnipper.OfficePlugin.Abstractions.FormulaIdentity", $true)
    $metadataType = $abstractionsAssembly.GetType("LaTeXSnipper.OfficePlugin.Abstractions.FormulaMetadata", $true)
    $displayModeType = $abstractionsAssembly.GetType("LaTeXSnipper.OfficePlugin.Abstractions.FormulaDisplayMode", $true)
    $numberingModeType = $abstractionsAssembly.GetType("LaTeXSnipper.OfficePlugin.Abstractions.NumberingMode", $true)
    $renderEngineType = $abstractionsAssembly.GetType("LaTeXSnipper.OfficePlugin.Abstractions.RenderEngineKind", $true)
    $fontStyleType = $abstractionsAssembly.GetType("LaTeXSnipper.OfficePlugin.Abstractions.FormulaFontStyle", $true)

    $identity = [Activator]::CreateInstance($identityType, @($DocumentId, $EquationId))
    [Activator]::CreateInstance(
        $metadataType,
        @(
            $identity,
            $Latex,
            [Enum]::Parse($displayModeType, $DisplayMode),
            [Enum]::Parse($numberingModeType, $NumberingMode),
            $NumberText,
            [Enum]::Parse($renderEngineType, $RenderEngine),
            1,
            $FontColor,
            [Enum]::Parse($fontStyleType, $FontStyle),
            $FontScale
        ))
}

function Invoke-StaticMethod {
    param(
        [Type]$Type,
        [string]$Name,
        [Parameter(ValueFromRemainingArguments = $true)]
        [object[]]$Arguments
    )

    $flags = [Reflection.BindingFlags]"Public,NonPublic,Static"
    $method = $Type.GetMethods($flags) |
        Where-Object { $_.Name -eq $Name -and $_.GetParameters().Count -eq $Arguments.Count } |
        Select-Object -First 1
    if ($null -eq $method) {
        throw "Missing method: $($Type.FullName).$Name/$($Arguments.Count)"
    }

    $method.Invoke($null, $Arguments)
}

function Assert-FormulaMetadata {
    param(
        $Metadata,
        [string]$EquationId,
        [string]$Latex,
        [string]$FontColor,
        [string]$FontStyle,
        [double]$FontScale,
        [string]$RenderEngine
    )

    if ($Metadata.Identity.EquationId -ne $EquationId) {
        throw "EquationId mismatch: $($Metadata.Identity.EquationId) != $EquationId"
    }
    if ($Metadata.Latex -ne $Latex) {
        throw "LaTeX mismatch: $($Metadata.Latex) != $Latex"
    }
    if ($Metadata.FontColor -ne $FontColor) {
        throw "Font color mismatch: $($Metadata.FontColor) != $FontColor"
    }
    if ($Metadata.FontStyle.ToString() -ne $FontStyle) {
        throw "Font style mismatch: $($Metadata.FontStyle) != $FontStyle"
    }
    if ([Math]::Abs([double]$Metadata.FontScale - $FontScale) -gt 0.0001) {
        throw "Font scale mismatch: $($Metadata.FontScale) != $FontScale"
    }
    if ($Metadata.RenderEngine.ToString() -ne $RenderEngine) {
        throw "Render engine mismatch: $($Metadata.RenderEngine) != $RenderEngine"
    }
}

function Invoke-OfficeUndo {
    param($Application)

    $Application.CommandBars.ExecuteMso("Undo") | Out-Null
    Start-Sleep -Milliseconds 300
}

function Test-WordFormulaMetadata {
    $wordApplication = $null
    $document = $null
    try {
        $metadataStore = $wordAssembly.GetType("LaTeXSnipper.OfficePlugin.WordAddIn.WordFormulaMetadataStore", $true)
        $wordApplication = New-Object -ComObject Word.Application
        $wordApplication.Visible = $true
        $document = $wordApplication.Documents.Add()

        $ommlMetadata = New-FormulaMetadata `
            -DocumentId "word-doc" `
            -EquationId "word-omml-inline" `
            -Latex "e^{i\pi}+1=0" `
            -DisplayMode "Inline" `
            -NumberingMode "None" `
            -NumberText "" `
            -RenderEngine "Omml" `
            -FontColor "#ff0000" `
            -FontStyle "RomanUpright" `
            -FontScale 1.25
        $contentControl = $document.Range(0, 0).ContentControls.Add(0)
        $contentControl.Range.Text = "e^{iπ}+1=0"
        $contentControl.Tag = Invoke-StaticMethod $metadataStore Save $document $ommlMetadata ([double]0) ([double]0)
        Assert-FormulaMetadata `
            (Invoke-StaticMethod $metadataStore Load $document ([string]$contentControl.Tag)) `
            "word-omml-inline" "e^{i\pi}+1=0" "#ff0000" "RomanUpright" 1.25 "Omml"

        $updatedOmmlMetadata = New-FormulaMetadata `
            -DocumentId "word-doc" `
            -EquationId "word-omml-inline" `
            -Latex "\mathrm{x+y}" `
            -DisplayMode "Inline" `
            -NumberingMode "None" `
            -NumberText "" `
            -RenderEngine "Omml" `
            -FontColor "#0055aa" `
            -FontStyle "Bold" `
            -FontScale 1.5
        $contentControl.Tag = Invoke-StaticMethod $metadataStore Save $document $updatedOmmlMetadata ([double]0) ([double]0)
        Assert-FormulaMetadata `
            (Invoke-StaticMethod $metadataStore Load $document ([string]$contentControl.Tag)) `
            "word-omml-inline" "\mathrm{x+y}" "#0055aa" "Bold" 1.5 "Omml"

        $contentControl.Range.Delete() | Out-Null
        Invoke-OfficeUndo $wordApplication
        $restoredControl = $document.ContentControls.Item(1)
        Assert-FormulaMetadata `
            (Invoke-StaticMethod $metadataStore Load $document ([string]$restoredControl.Tag)) `
            "word-omml-inline" "\mathrm{x+y}" "#0055aa" "Bold" 1.5 "Omml"
        Write-Output "Word OMML ContentControl metadata save/update/delete-undo OK"

        $oleMetadata = New-FormulaMetadata `
            -DocumentId "word-doc" `
            -EquationId "word-ole-inline" `
            -Latex "\color{#00aa00}{x^2}" `
            -DisplayMode "Inline" `
            -NumberingMode "None" `
            -NumberText "" `
            -RenderEngine "MathJaxSvg" `
            -FontColor "#00aa00" `
            -FontStyle "Italic" `
            -FontScale 1.1
        $oleTag = Invoke-StaticMethod $metadataStore Save $document $oleMetadata ([double]42.5) ([double]18.25)
        $shape = $document.Shapes.AddShape(1, 10, 10, 40, 20)
        $shape.AlternativeText = $oleTag
        Assert-FormulaMetadata `
            (Invoke-StaticMethod $metadataStore Load $document ([string]$shape.AlternativeText)) `
            "word-ole-inline" "\color{#00aa00}{x^2}" "#00aa00" "Italic" 1.1 "MathJaxSvg"

        $tryLoadNaturalSize = $metadataStore.GetMethod("TryLoadOleNaturalSize", [Reflection.BindingFlags]"Public,NonPublic,Static")
        $naturalSizeArgs = @($document, [string]$shape.AlternativeText, [double]0, [double]0)
        $naturalSizeLoaded = $tryLoadNaturalSize.Invoke($null, $naturalSizeArgs)
        if (-not $naturalSizeLoaded -or
            [Math]::Abs([double]$naturalSizeArgs[2] - 42.5) -gt 0.001 -or
            [Math]::Abs([double]$naturalSizeArgs[3] - 18.25) -gt 0.001) {
            throw "Word OLE natural size metadata failed."
        }

        $shape.Delete() | Out-Null
        Invoke-OfficeUndo $wordApplication
        $restoredShape = $document.Shapes.Item(1)
        Assert-FormulaMetadata `
            (Invoke-StaticMethod $metadataStore Load $document ([string]$restoredShape.AlternativeText)) `
            "word-ole-inline" "\color{#00aa00}{x^2}" "#00aa00" "Italic" 1.1 "MathJaxSvg"
        Write-Output "Word OLE AlternativeText metadata natural-size/delete-undo OK"
    }
    finally {
        if ($null -ne $document) {
            $document.Close($false) | Out-Null
        }
        if ($null -ne $wordApplication) {
            $wordApplication.Quit() | Out-Null
        }
    }
}

function Test-PowerPointFormulaMetadata {
    Add-Type -AssemblyName System.Windows.Forms

    $powerPointApplication = $null
    $presentation = $null
    try {
        $metadataStore = $powerPointAssembly.GetType("LaTeXSnipper.OfficePlugin.PowerPointAddIn.PowerPointFormulaMetadataStore", $true)
        $powerPointApplication = New-Object -ComObject PowerPoint.Application
        $powerPointApplication.Visible = -1
        $presentation = $powerPointApplication.Presentations.Add()
        $slide = $presentation.Slides.Add(1, 12)
        $powerPointApplication.ActiveWindow.View.GotoSlide(1)

        $shape = $slide.Shapes.AddShape(1, 50, 50, 120, 40)
        $longLatex = ("\frac{\partial f}{\partial x_i}+" * 80) + "0"
        $metadata = New-FormulaMetadata `
            -DocumentId "ppt-doc" `
            -EquationId "ppt-shape-1" `
            -Latex $longLatex `
            -DisplayMode "Display" `
            -NumberingMode "None" `
            -NumberText "" `
            -RenderEngine "MathJaxSvg" `
            -FontColor "#336699" `
            -FontStyle "Bold" `
            -FontScale 1.35
        Invoke-StaticMethod $metadataStore ApplyToShape $shape $metadata ([single]120) ([single]40) | Out-Null
        Assert-FormulaMetadata `
            (Invoke-StaticMethod $metadataStore LoadFromShape $shape) `
            "ppt-shape-1" $longLatex "#336699" "Bold" 1.35 "MathJaxSvg"

        $updatedMetadata = New-FormulaMetadata `
            -DocumentId "ppt-doc" `
            -EquationId "ppt-shape-1" `
            -Latex "\bm{F=ma}" `
            -DisplayMode "Display" `
            -NumberingMode "None" `
            -NumberText "" `
            -RenderEngine "Image" `
            -FontColor "#aa5500" `
            -FontStyle "Italic" `
            -FontScale 1.2
        Invoke-StaticMethod $metadataStore ApplyToShape $shape $updatedMetadata ([single]130) ([single]44) | Out-Null
        Assert-FormulaMetadata `
            (Invoke-StaticMethod $metadataStore LoadFromShape $shape) `
            "ppt-shape-1" "\bm{F=ma}" "#aa5500" "Italic" 1.2 "Image"

        $duplicate = $shape.Duplicate().Item(1)
        Assert-FormulaMetadata `
            (Invoke-StaticMethod $metadataStore LoadFromShape $duplicate) `
            "ppt-shape-1" "\bm{F=ma}" "#aa5500" "Italic" 1.2 "Image"

        $shape.Select()
        Start-Sleep -Milliseconds 300
        [System.Windows.Forms.SendKeys]::SendWait("{DELETE}")
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.SendKeys]::SendWait("^z")
        Start-Sleep -Milliseconds 800

        $found = $false
        for ($index = 1; $index -le $slide.Shapes.Count; $index++) {
            try {
                $candidateMetadata = Invoke-StaticMethod $metadataStore LoadFromShape $slide.Shapes.Item($index)
                if ($candidateMetadata.Identity.EquationId -eq "ppt-shape-1") {
                    Assert-FormulaMetadata $candidateMetadata "ppt-shape-1" "\bm{F=ma}" "#aa5500" "Italic" 1.2 "Image"
                    $found = $true
                    break
                }
            }
            catch {
            }
        }
        if (-not $found) {
            throw "PowerPoint UI Delete/Ctrl+Z did not restore formula metadata."
        }
        Write-Output "PowerPoint shape metadata long-latex/update/duplicate/delete-undo OK"
    }
    finally {
        if ($null -ne $presentation) {
            $presentation.Close() | Out-Null
        }
        if ($null -ne $powerPointApplication) {
            $powerPointApplication.Quit() | Out-Null
        }
    }
}

if (-not $SkipWord) {
    Test-WordFormulaMetadata
}

if (-not $SkipPowerPoint) {
    Test-PowerPointFormulaMetadata
}
