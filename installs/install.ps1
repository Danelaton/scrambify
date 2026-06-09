$ErrorActionPreference = "Stop"

$Repo = "Danelaton/scrambify"
$ApiUrl = "https://api.github.com/repos/$Repo/releases/latest"
$InstallRoot = Join-Path $env:LOCALAPPDATA "scrambify"
$InstallDir = Join-Path $InstallRoot "bin"
$BinaryName = "scrambify.exe"

function Write-Phase {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Yellow
}

function Get-LatestVersion {
    $release = Invoke-RestMethod -Uri $ApiUrl
    if (-not $release.tag_name) {
        throw "Unable to determine the latest release"
    }
    return [string]$release.tag_name
}

function Ensure-PathEntry {
    param([string]$PathEntry)

    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $segments = @()
    if ($currentPath) {
        $segments = $currentPath.Split(';', [System.StringSplitOptions]::RemoveEmptyEntries)
    }
    if ($segments -contains $PathEntry) {
        return $false
    }
    $updated = if ($currentPath) { "$currentPath;$PathEntry" } else { $PathEntry }
    [Environment]::SetEnvironmentVariable("Path", $updated, "User")
    return $true
}

Write-Phase "Detecting platform"
$Version = Get-LatestVersion
$AssetName = "scrambify_${Version}_windows_amd64.zip"
$DownloadUrl = "https://github.com/$Repo/releases/download/$Version/$AssetName"
Write-Info "Latest release: $Version"
Write-Info "Target asset: $AssetName"

Write-Phase "Preparing installation directory"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("scrambify-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
$ArchivePath = Join-Path $TempDir $AssetName

try {
    Write-Phase "Downloading release archive"
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $ArchivePath

    Write-Phase "Extracting archive"
    Expand-Archive -Path $ArchivePath -DestinationPath $TempDir -Force
    $ExtractedBinary = Join-Path $TempDir $BinaryName
    if (-not (Test-Path $ExtractedBinary)) {
        throw "Archive did not contain $BinaryName"
    }

    Write-Phase "Installing binary"
    Copy-Item -Force $ExtractedBinary (Join-Path $InstallDir $BinaryName)
    $PathUpdated = Ensure-PathEntry $InstallDir

    Write-Phase "Summary"
    Write-Info "Installed $BinaryName to $(Join-Path $InstallDir $BinaryName)"
    if ($PathUpdated) {
        Write-Warn "Added $InstallDir to the user PATH. Restart your shell to pick it up."
    } else {
        Write-Info "$InstallDir is already on PATH"
    }
    Write-Info "Run 'scrambify --help' to verify the installation"
}
finally {
    if (Test-Path $TempDir) {
        Remove-Item -Recurse -Force $TempDir
    }
}