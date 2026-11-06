[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$ReleaseTag,

  [Parameter(Mandatory = $true)]
  [string]$ReleaseCommit,

  [string]$ChecksumsPath = 'artifacts/checksums.json',

  [string]$UpstreamReleasePath = '.github/upstream-stable-release',

  [string]$UpstreamCommitPath = '.github/upstream-stable-commit',

  [string]$OutputPath = 'release-notes.md'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $ChecksumsPath -PathType Leaf)) {
  throw "Checksum metadata not found: $ChecksumsPath"
}

if (-not (Test-Path -LiteralPath $UpstreamReleasePath -PathType Leaf)) {
  throw "Upstream release state not found: $UpstreamReleasePath"
}

$upstreamRelease = [System.IO.File]::ReadAllText(
  [System.IO.Path]::GetFullPath($UpstreamReleasePath),
  [System.Text.Encoding]::UTF8
).Trim()
if ([string]::IsNullOrWhiteSpace($upstreamRelease)) {
  throw "Upstream release state is empty: $UpstreamReleasePath"
}

if (-not (Test-Path -LiteralPath $UpstreamCommitPath -PathType Leaf)) {
  throw "Upstream commit state not found: $UpstreamCommitPath"
}
$upstreamCommit = [System.IO.File]::ReadAllText(
  [System.IO.Path]::GetFullPath($UpstreamCommitPath),
  [System.Text.Encoding]::UTF8
).Trim()
if ($upstreamCommit -notmatch '\A[0-9a-fA-F]{40}\z') {
  throw "Upstream commit state must contain a full Git commit SHA: $UpstreamCommitPath"
}
$upstreamCommit = $upstreamCommit.ToLowerInvariant()
if ($ReleaseCommit -notmatch '\A[0-9a-fA-F]{40}\z') {
  throw 'ReleaseCommit must be a full Git commit SHA.'
}

$parsedChecksumEntries = [System.IO.File]::ReadAllText(
  [System.IO.Path]::GetFullPath($ChecksumsPath),
  [System.Text.Encoding]::UTF8
) | ConvertFrom-Json
$checksumEntries = @()
foreach ($entry in $parsedChecksumEntries) {
  $checksumEntries += $entry
}
$installer = @($checksumEntries | Where-Object { $_.File -like '*.WindowsInstaller.exe' })
$portable = @($checksumEntries | Where-Object { $_.File -like '*.Portable-x64.zip' })

if ($installer.Count -ne 1 -or $portable.Count -ne 1) {
  throw 'Release notes require exactly one Windows installer and one portable package.'
}

$packageEntries = @($installer[0], $portable[0])
$checksumLines = @(
  $packageEntries | ForEach-Object {
    '{0}  {1}' -f ([string]$_.Hash).ToLowerInvariant(), $_.File
  }
)

$templatePath = Join-Path $PSScriptRoot 'app-display-release-notes-template.md'
if (-not (Test-Path -LiteralPath $templatePath -PathType Leaf)) {
  throw "Release notes template not found: $templatePath"
}

$content = [System.IO.File]::ReadAllText($templatePath, [System.Text.Encoding]::UTF8)
$replacements = [ordered]@{
  '{{RELEASE_TAG}}' = $ReleaseTag
  '{{UPSTREAM_RELEASE}}' = $upstreamRelease
  '{{UPSTREAM_COMMIT}}' = $upstreamCommit
  '{{UPSTREAM_RELEASE_URL}}' = 'https://github.com/AlkaidLab/foundation-sunshine/releases/tag/' + [System.Uri]::EscapeDataString($upstreamRelease)
  '{{INSTALLER_FILE}}' = [string]($installer[0].File)
  '{{PORTABLE_FILE}}' = [string]($portable[0].File)
  '{{CHECKSUM_LINES}}' = ($checksumLines -join "`n")
  '{{RELEASE_COMMIT}}' = $ReleaseCommit
}
foreach ($replacement in $replacements.GetEnumerator()) {
  $content = $content.Replace([string]$replacement.Key, [string]$replacement.Value)
}
if ($content -match '\{\{[A-Z_]+\}\}') {
  throw "Release notes template contains an unresolved placeholder: $($Matches[0])"
}

$outputDirectory = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($outputDirectory)) {
  [System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
}

if (-not $content.EndsWith("`n")) {
  $content += "`n"
}
[System.IO.File]::WriteAllText(
  [System.IO.Path]::GetFullPath($OutputPath),
  $content,
  [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Release notes saved to: $OutputPath"
