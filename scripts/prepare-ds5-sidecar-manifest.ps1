[CmdletBinding()]
param(
  [string]$Repository = 'AlkaidLab/foundation-sunshine',
  [string]$ReleaseTagPath = '.github/upstream-stable-release',
  [string]$ControlPanelSourcePath = 'src_assets/common/sunshine-control-panel/src-tauri/src/dualsense.rs',
  [string]$ControlPanelCompatibilityPath = 'src_assets/common/sunshine-control-panel/src-tauri/component-compatibility.json',
  [string]$OutputPath = 'build/ds5-sidecar-package.json',
  [string]$ReleaseMetadataPath = '',
  [string]$ManifestSourcePath = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$repositoryPrefix = $repositoryRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

function Resolve-RepositoryPath([string]$Path, [string]$Description) {
  if ([System.IO.Path]::IsPathRooted($Path)) {
    $resolved = [System.IO.Path]::GetFullPath($Path)
  }
  else {
    $resolved = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $Path))
  }
  if ($resolved -ne $repositoryRoot -and
      -not $resolved.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "$Description must remain inside the repository: $resolved"
  }
  return $resolved
}

function Read-RustStringConstant([string]$Source, [string]$Name) {
  $pattern = 'const\s+' + [regex]::Escape($Name) + '\s*:\s*&str\s*=\s*"([^"]+)"\s*;'
  $match = [regex]::Match($Source, $pattern)
  if (-not $match.Success) {
    throw "Unable to read $Name from the pinned Control Panel source."
  }
  return $match.Groups[1].Value
}

function Read-RustUIntConstant([string]$Source, [string]$Name) {
  $pattern = 'const\s+' + [regex]::Escape($Name) + '\s*:\s*u32\s*=\s*([0-9]+)\s*;'
  $match = [regex]::Match($Source, $pattern)
  if (-not $match.Success) {
    throw "Unable to read $Name from the pinned Control Panel source."
  }
  return [uint32]$match.Groups[1].Value
}

function Get-RequiredAsset([object]$Release, [string]$Name) {
  $matches = @($Release.assets | Where-Object { [string]$_.name -ceq $Name })
  if ($matches.Count -ne 1) {
    throw "Upstream release must contain exactly one $Name asset."
  }
  return $matches[0]
}

function Get-AssetSha256([object]$Asset) {
  $digest = [string]$Asset.digest
  if ($digest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
    throw "GitHub did not provide a valid SHA256 digest for $($Asset.name)."
  }
  return $Matches[1].ToLowerInvariant()
}

$releaseTagFile = Resolve-RepositoryPath $ReleaseTagPath 'Upstream release state file'
$compatibilityFile = Resolve-RepositoryPath $ControlPanelCompatibilityPath 'Control Panel compatibility manifest'
# The pinned control panel moved the DualSense sidecar constants from the
# single dualsense.rs module into dualsense/mod.rs. Probe the new layout first
# and fall back to the legacy file so both pins keep working. Its component
# version comes from component-compatibility.json through build.rs.
$controlPanelSourceFile = Resolve-RepositoryPath $ControlPanelSourcePath 'Control Panel source file'
if (-not (Test-Path -LiteralPath $controlPanelSourceFile -PathType Leaf)) {
  $moduleSource = Join-Path (Split-Path -Parent $controlPanelSourceFile) 'dualsense/mod.rs'
  if (Test-Path -LiteralPath $moduleSource -PathType Leaf) {
    $controlPanelSourceFile = $moduleSource
  }
}
$outputFile = Resolve-RepositoryPath $OutputPath 'Manifest output path'

if (-not (Test-Path -LiteralPath $releaseTagFile -PathType Leaf)) {
  throw "Upstream release state file is missing: $releaseTagFile"
}
if (-not (Test-Path -LiteralPath $compatibilityFile -PathType Leaf)) {
  throw "Control Panel compatibility manifest is missing: $compatibilityFile"
}
if (-not (Test-Path -LiteralPath $controlPanelSourceFile -PathType Leaf)) {
  throw "Pinned Control Panel source is missing: $controlPanelSourceFile"
}

$releaseTag = [System.IO.File]::ReadAllText($releaseTagFile, [System.Text.Encoding]::UTF8).Trim()
if ([string]::IsNullOrWhiteSpace($releaseTag)) {
  throw "Upstream release state file is empty: $releaseTagFile"
}

$controlPanelSource = [System.IO.File]::ReadAllText($controlPanelSourceFile, [System.Text.Encoding]::UTF8)
$compatibility = [System.IO.File]::ReadAllText($compatibilityFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
if ([uint32]$compatibility.schema -ne 1 -or [string]::IsNullOrWhiteSpace([string]$compatibility.component_version)) {
  throw "Control Panel compatibility manifest has an invalid component version: $compatibilityFile"
}
$expectedComponentVersion = [string]$compatibility.component_version
$expectedProtocol = Read-RustUIntConstant $controlPanelSource 'PROTOCOL_VERSION'
$expectedAssetName = Read-RustStringConstant $controlPanelSource 'SIDECAR_PACKAGE_ASSET'
$expectedTarget = Read-RustStringConstant $controlPanelSource 'SIDECAR_PACKAGE_TARGET'
$expectedLicense = Read-RustStringConstant $controlPanelSource 'SIDECAR_PACKAGE_LICENSE'
$manifestAssetName = 'Sunshine.Ds5Sidecar.manifest.json'

$headers = @{
  Accept = 'application/vnd.github+json'
  'User-Agent' = 'Sunshine-AppDisplayProfile-Packager'
  'X-GitHub-Api-Version' = '2022-11-28'
}
if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
  $headers.Authorization = "Bearer $($env:GITHUB_TOKEN)"
}

if (-not [string]::IsNullOrWhiteSpace($ReleaseMetadataPath)) {
  $releaseMetadataFile = Resolve-RepositoryPath $ReleaseMetadataPath 'Release metadata fixture'
  $release = [System.IO.File]::ReadAllText($releaseMetadataFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
}
else {
  $escapedTag = [System.Uri]::EscapeDataString($releaseTag)
  $releaseApi = "https://api.github.com/repos/$Repository/releases/tags/$escapedTag"
  $release = Invoke-RestMethod -Uri $releaseApi -Headers $headers
}

if ([string]$release.tag_name -cne $releaseTag -or [bool]$release.draft -or [bool]$release.prerelease) {
  throw "Pinned upstream tag is not an available formal release: $releaseTag"
}

$manifestAsset = Get-RequiredAsset $release $manifestAssetName
$packageAsset = Get-RequiredAsset $release $expectedAssetName
$manifestAssetSha256 = Get-AssetSha256 $manifestAsset
$packageAssetSha256 = Get-AssetSha256 $packageAsset

$temporaryManifest = $null
try {
  if (-not [string]::IsNullOrWhiteSpace($ManifestSourcePath)) {
    $manifestFile = Resolve-RepositoryPath $ManifestSourcePath 'Manifest fixture'
  }
  else {
    $temporaryManifest = Join-Path ([System.IO.Path]::GetTempPath()) ('sunshine-ds5-manifest-' + [guid]::NewGuid().ToString('N') + '.json')
    Invoke-WebRequest -Uri ([string]$manifestAsset.browser_download_url) -Headers $headers -OutFile $temporaryManifest -UseBasicParsing
    $manifestFile = $temporaryManifest
  }

  if (-not (Test-Path -LiteralPath $manifestFile -PathType Leaf)) {
    throw "DualSense manifest source is missing: $manifestFile"
  }
  $actualManifestSha256 = (Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actualManifestSha256 -cne $manifestAssetSha256) {
    throw "DualSense manifest digest mismatch: expected $manifestAssetSha256, got $actualManifestSha256"
  }

  $manifest = [System.IO.File]::ReadAllText($manifestFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
  $validManifest =
    [uint32]$manifest.schema -eq 1 -and
    [string]$manifest.component_version -ceq $expectedComponentVersion -and
    [uint32]$manifest.protocol -eq $expectedProtocol -and
    [string]$manifest.target -ceq $expectedTarget -and
    [string]$manifest.license -ceq $expectedLicense -and
    [string]$manifest.asset_name -ceq $expectedAssetName -and
    [string]$manifest.download_url -ceq [string]$packageAsset.browser_download_url -and
    [string]$manifest.sha256 -ceq $packageAssetSha256 -and
    [uint64]$manifest.size -eq [uint64]$packageAsset.size
  if (-not $validManifest) {
    throw 'The upstream DualSense manifest does not match the pinned Control Panel or release asset metadata.'
  }

  $outputDirectory = Split-Path -Parent $outputFile
  [System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
  [System.IO.File]::WriteAllBytes($outputFile, [System.IO.File]::ReadAllBytes($manifestFile))
}
finally {
  if ($null -ne $temporaryManifest -and (Test-Path -LiteralPath $temporaryManifest)) {
    Remove-Item -LiteralPath $temporaryManifest -Force
  }
}

Write-Host "Prepared pinned DualSense manifest for $releaseTag`: $outputFile"
