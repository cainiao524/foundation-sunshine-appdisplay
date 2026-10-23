[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$testRoot = Join-Path $repositoryRoot ('build/test-ds5-manifest-' + [guid]::NewGuid().ToString('N'))
$statePath = Join-Path $testRoot 'upstream-release.txt'
$manifestPath = Join-Path $testRoot 'manifest.json'
$metadataPath = Join-Path $testRoot 'release.json'
$outputPath = Join-Path $testRoot 'output.json'
$releaseTag = [System.IO.File]::ReadAllText(
  (Join-Path $repositoryRoot '.github/upstream-stable-release'),
  [System.Text.Encoding]::UTF8
).Trim()
$compatibility = [System.IO.File]::ReadAllText(
  (Join-Path $repositoryRoot 'src_assets/common/sunshine-control-panel/src-tauri/component-compatibility.json'),
  [System.Text.Encoding]::UTF8
) | ConvertFrom-Json
$componentVersion = [string]$compatibility.component_version
$packageName = 'Sunshine.Ds5Sidecar.x64.zip'
$manifestName = 'Sunshine.Ds5Sidecar.manifest.json'
$packageUrl = "https://github.com/AlkaidLab/foundation-sunshine/releases/download/$([System.Uri]::EscapeDataString($releaseTag))/$packageName"
$packageSha256 = '5415333fe83f7fd2c6d68f9178fa6a525a3b23092f76077f5db688c57fbe38a1'
$packageSize = 43915484

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  [System.IO.File]::WriteAllText(
    $Path,
    $Content,
    [System.Text.UTF8Encoding]::new($false)
  )
}

function Write-Fixture([string]$ComponentVersion, [string]$DownloadUrl) {
  $manifest = [ordered]@{
    schema = 1
    component_version = $ComponentVersion
    protocol = 1
    target = 'win-x64-self-contained'
    license = 'GPL-3.0-only'
    asset_name = $packageName
    download_url = $DownloadUrl
    sha256 = $packageSha256
    size = $packageSize
  }
  Write-Utf8NoBom $manifestPath (($manifest | ConvertTo-Json) + "`n")
  $manifestSha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
  $release = [ordered]@{
    tag_name = $releaseTag
    draft = $false
    prerelease = $false
    assets = @(
      [ordered]@{
        name = $manifestName
        digest = "sha256:$manifestSha256"
        size = (Get-Item -LiteralPath $manifestPath).Length
        browser_download_url = "https://github.com/AlkaidLab/foundation-sunshine/releases/download/$([System.Uri]::EscapeDataString($releaseTag))/$manifestName"
      },
      [ordered]@{
        name = $packageName
        digest = "sha256:$packageSha256"
        size = $packageSize
        browser_download_url = $packageUrl
      }
    )
  }
  Write-Utf8NoBom $metadataPath (($release | ConvertTo-Json -Depth 5) + "`n")
}

function Invoke-PrepareManifest {
  & (Join-Path $PSScriptRoot 'prepare-ds5-sidecar-manifest.ps1') `
    -ReleaseTagPath $statePath `
    -ReleaseMetadataPath $metadataPath `
    -ManifestSourcePath $manifestPath `
    -OutputPath $outputPath
}

function Assert-Rejected([scriptblock]$Action, [string]$Description) {
  $rejected = $false
  try {
    & $Action
  }
  catch {
    $rejected = $true
  }
  if (-not $rejected) {
    throw "Invalid fixture was accepted: $Description"
  }
}

try {
  New-Item -ItemType Directory -Path $testRoot | Out-Null
  Write-Utf8NoBom $statePath ($releaseTag + "`n")

  Write-Fixture -ComponentVersion $componentVersion -DownloadUrl $packageUrl
  Invoke-PrepareManifest
  if ((Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash -cne
      (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash) {
    throw 'Prepared manifest differs from the verified upstream manifest.'
  }

  Write-Fixture -ComponentVersion $componentVersion -DownloadUrl 'https://github.com/AlkaidLab/foundation-sunshine/releases/download/v1.6.%E6%9D%82%E9%B1%BC/Sunshine.Ds5Sidecar.x64.zip'
  Assert-Rejected { Invoke-PrepareManifest } 'dead downstream-derived download URL'

  Write-Fixture -ComponentVersion '1.0.0' -DownloadUrl $packageUrl
  Assert-Rejected { Invoke-PrepareManifest } 'Control Panel component version mismatch'

  Write-Fixture -ComponentVersion $componentVersion -DownloadUrl $packageUrl
  $tamperedRelease = [System.IO.File]::ReadAllText($metadataPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
  $tamperedRelease.assets[1].digest = 'sha256:' + ('b' * 64)
  Write-Utf8NoBom $metadataPath (($tamperedRelease | ConvertTo-Json -Depth 5) + "`n")
  Assert-Rejected { Invoke-PrepareManifest } 'Sidecar release digest mismatch'
}
finally {
  if (Test-Path -LiteralPath $testRoot) {
    Remove-Item -LiteralPath $testRoot -Recurse -Force
  }
}

Write-Host 'DualSense manifest preparation tests passed.'
