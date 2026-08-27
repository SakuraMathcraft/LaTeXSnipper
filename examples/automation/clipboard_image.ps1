param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

$dataObject = [System.Windows.Forms.Clipboard]::GetDataObject()
$image = [System.Windows.Forms.Clipboard]::GetImage()
$imageStream = $null
if ($null -eq $image -and $null -ne $dataObject -and $dataObject.GetDataPresent("PNG")) {
    $imageStream = $dataObject.GetData("PNG")
    if ($imageStream -is [System.IO.Stream]) {
        $image = [System.Drawing.Image]::FromStream($imageStream)
    }
}
if ($null -eq $image) {
    [Console]::Error.WriteLine("The clipboard does not contain image data.")
    exit 2
}

try {
    $directory = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($OutputPath))
    if (-not [System.IO.Directory]::Exists($directory)) {
        [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    }
    $image.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $image.Dispose()
    if ($null -ne $imageStream) {
        $imageStream.Dispose()
    }
}
