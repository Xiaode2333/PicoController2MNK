$ErrorActionPreference = "Stop"

function New-MultiSizeWindowsIcon {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PngPath,

        [Parameter(Mandatory = $true)]
        [string]$IcoPath
    )

    if (-not (Test-Path -LiteralPath $PngPath -PathType Leaf)) {
        throw "Missing app icon source: $PngPath"
    }

    Add-Type -AssemblyName System.Drawing

    $iconSizes = [int[]](16, 20, 24, 32, 40, 48, 64, 128, 256)
    $pngEntries = New-Object System.Collections.ArrayList
    $sourceImage = [System.Drawing.Image]::FromFile($PngPath)
    try {
        if ($sourceImage.Width -ne $sourceImage.Height) {
            throw "App icon must be square; received $($sourceImage.Width)x$($sourceImage.Height): $PngPath"
        }

        foreach ($iconSize in $iconSizes) {
            $bitmap = [System.Drawing.Bitmap]::new(
                $iconSize,
                $iconSize,
                [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
            )
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            $pngStream = [System.IO.MemoryStream]::new()
            try {
                $graphics.Clear([System.Drawing.Color]::Transparent)
                $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
                $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
                $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
                $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $graphics.DrawImage(
                    $sourceImage,
                    [System.Drawing.Rectangle]::new(0, 0, $iconSize, $iconSize)
                )
                $bitmap.Save($pngStream, [System.Drawing.Imaging.ImageFormat]::Png)
                [void]$pngEntries.Add($pngStream.ToArray())
            } finally {
                $pngStream.Dispose()
                $graphics.Dispose()
                $bitmap.Dispose()
            }
        }
    } finally {
        $sourceImage.Dispose()
    }

    $icoStream = [System.IO.MemoryStream]::new()
    $binaryWriter = [System.IO.BinaryWriter]::new($icoStream)
    try {
        # ICONDIR header: reserved, image type, image count.
        $binaryWriter.Write([uint16]0)
        $binaryWriter.Write([uint16]1)
        $binaryWriter.Write([uint16]$iconSizes.Length)

        $dataOffset = 6 + (16 * $iconSizes.Length)
        for ($iconIndex = 0; $iconIndex -lt $iconSizes.Length; $iconIndex++) {
            $iconSize = $iconSizes[$iconIndex]
            $dimensionByte = if ($iconSize -ge 256) { [byte]0 } else { [byte]$iconSize }
            $pngEntry = [byte[]]$pngEntries[$iconIndex]

            # ICONDIRENTRY. A dimension byte of zero means 256 pixels.
            $binaryWriter.Write($dimensionByte)
            $binaryWriter.Write($dimensionByte)
            $binaryWriter.Write([byte]0)
            $binaryWriter.Write([byte]0)
            $binaryWriter.Write([uint16]1)
            $binaryWriter.Write([uint16]32)
            $binaryWriter.Write([uint32]$pngEntry.Length)
            $binaryWriter.Write([uint32]$dataOffset)
            $dataOffset += $pngEntry.Length
        }

        foreach ($pngEntryObject in $pngEntries) {
            $binaryWriter.Write([byte[]]$pngEntryObject)
        }
        $binaryWriter.Flush()
        $icoBytes = $icoStream.ToArray()
    } finally {
        $binaryWriter.Dispose()
        $icoStream.Dispose()
    }

    [System.IO.File]::WriteAllBytes($IcoPath, $icoBytes)
    Write-Host "Generated app icon: $IcoPath ($($iconSizes -join ', ') px)"
}

$root = (Resolve-Path (Join-Path $PSScriptRoot ".")).Path
$spec = Join-Path $root "packaging\windows\PicoController2MNK.spec"
$iss = Join-Path $root "packaging\windows\PicoController2MNK.iss"
$uf2 = Join-Path $root "build\pico_kbm_mapper.uf2"
$iconPng = Join-Path $root "assets\icon.png"
$iconIco = Join-Path $root "assets\icon.ico"

if (-not (Test-Path $uf2)) {
    throw "Missing $uf2. Build the stable firmware first with build_firmware.bat."
}

New-MultiSizeWindowsIcon -PngPath $iconPng -IcoPath $iconIco

if (-not (Get-Command poetry -ErrorAction SilentlyContinue)) {
    throw "Poetry is not installed or is not on PATH."
}

try {
    & poetry run python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "missing"
    }
} catch {
    throw "PyInstaller is not installed in the Poetry environment. Run: poetry run pip install pyinstaller"
}

$isccCommand = Get-Command iscc.exe -ErrorAction SilentlyContinue
if ($isccCommand) {
    $isccPath = $isccCommand.Source
} else {
    $defaultIscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
    if (Test-Path $defaultIscc) {
        $isccPath = $defaultIscc
    } else {
        throw "Inno Setup 6 (ISCC.exe) is not installed."
    }
}

Push-Location $root
try {
    & poetry run pyinstaller --noconfirm --clean $spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $bundledIcon = Join-Path $root "dist\PicoController2MNK\_internal\assets\icon.ico"
    if (-not (Test-Path -LiteralPath $bundledIcon -PathType Leaf)) {
        throw "PyInstaller output is missing the bundled app icon: $bundledIcon"
    }
    $sourceIconHash = (Get-FileHash -LiteralPath $iconIco -Algorithm SHA256).Hash
    $bundledIconHash = (Get-FileHash -LiteralPath $bundledIcon -Algorithm SHA256).Hash
    if ($sourceIconHash -ne $bundledIconHash) {
        throw "Bundled app icon does not match the generated icon."
    }

    & $isccPath $iss
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$installer = Join-Path $root "installer\PicoController2MNK-Setup-0.1.2.exe"
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "Installer build completed without producing: $installer"
}
Write-Host "Verified bundled icon: $bundledIcon"
Write-Host "Created: $installer"
