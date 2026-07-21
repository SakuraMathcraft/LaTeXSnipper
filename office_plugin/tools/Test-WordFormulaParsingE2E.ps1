[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Debug',

    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\tests\LaTeXSnipper.OfficePlugin.WordParsingE2E\artifacts')
)

$ErrorActionPreference = 'Stop'
$projectPath = Join-Path $PSScriptRoot '..\tests\LaTeXSnipper.OfficePlugin.WordParsingE2E\LaTeXSnipper.OfficePlugin.WordParsingE2E.csproj'
$resolvedOutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)

function Wait-WordProcessExit {
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while (Get-Process -Name WINWORD -ErrorAction SilentlyContinue) {
        if ([DateTime]::UtcNow -ge $deadline) {
            throw '前一个 Word 测试实例未能在 20 秒内退出。'
        }

        Start-Sleep -Milliseconds 200
    }
}

if (Get-Process -Name WINWORD -ErrorAction SilentlyContinue) {
    throw '请先关闭所有 Microsoft Word 窗口，以便测试使用隔离的 Word 实例。'
}

New-Item -ItemType Directory -Path $resolvedOutputDirectory -Force | Out-Null
dotnet build $projectPath -c $Configuration
if ($LASTEXITCODE -ne 0) {
    throw "Word 公式解析端到端测试项目编译失败，退出码：$LASTEXITCODE。"
}

$executable = Join-Path (Split-Path $projectPath) "bin\$Configuration\net48\LaTeXSnipper.OfficePlugin.WordParsingE2E.exe"
$cases = @(
    @{ Backend = 'omml'; FileName = 'word_formula_parsing_e2e_omml.docx' },
    @{ Backend = 'ole'; FileName = 'word_formula_parsing_e2e_ole.docx' }
)

foreach ($case in $cases) {
    $outputPath = Join-Path $resolvedOutputDirectory $case.FileName
    & $executable --backend $case.Backend --output $outputPath
    if ($LASTEXITCODE -ne 0) {
        throw "Word 公式解析 $($case.Backend) 端到端测试失败，退出码：$LASTEXITCODE。"
    }

    Wait-WordProcessExit
}

Write-Host "Word 公式解析 OMML/OLE 端到端测试全部通过。"
