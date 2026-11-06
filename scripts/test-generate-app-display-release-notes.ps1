[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $repositoryRoot ('build/test-release-notes-' + [guid]::NewGuid().ToString('N'))
$checksumsPath = Join-Path $testRoot 'checksums.json'
$upstreamReleasePath = Join-Path $testRoot 'upstream-release'
$upstreamCommitPath = Join-Path $testRoot 'upstream-commit'
$outputPath = Join-Path $testRoot 'release-notes.md'
$upstreamCommit = '1234567890abcdef1234567890abcdef12345678'
$releaseCommit = 'abcdef1234567890abcdef1234567890abcdef12'
$installerHash = 'a' * 64
$portableHash = 'b' * 64

function Write-Fixture([string]$Path, [string]$Content) {
  [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Invoke-GenerateNotes {
  & (Join-Path $PSScriptRoot 'generate-app-display-release-notes.ps1') `
    -ReleaseTag 'v4.9' `
    -ReleaseCommit $releaseCommit `
    -ChecksumsPath $checksumsPath `
    -UpstreamReleasePath $upstreamReleasePath `
    -UpstreamCommitPath $upstreamCommitPath `
    -OutputPath $outputPath
}

function Assert-Rejected([scriptblock]$Action, [string]$ExpectedMessage) {
  try {
    & $Action
  }
  catch {
    if ($_.Exception.Message -notlike "*$ExpectedMessage*") { throw }
    return
  }
  throw "Invalid fixture was accepted; expected: $ExpectedMessage"
}

try {
  New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
  $checksums = @(
    @{ File = 'Sunshine.v4.9.WindowsInstaller.exe'; Hash = $installerHash }
    @{ File = 'Sunshine.v4.9.Portable-x64.zip'; Hash = $portableHash }
  )
  Write-Fixture $checksumsPath ($checksums | ConvertTo-Json)
  Write-Fixture $upstreamReleasePath "v2027.0101.123456.杂鱼`n"
  Write-Fixture $upstreamCommitPath ($upstreamCommit.ToUpperInvariant() + "`n")
  Invoke-GenerateNotes
  $notes = [System.IO.File]::ReadAllText($outputPath)
  foreach ($expected in @(
      'Sunshine App Display Profile v4.9',
      'v2027.0101.123456.杂鱼',
      'https://github.com/AlkaidLab/foundation-sunshine/releases/tag/v2027.0101.123456.%E6%9D%82%E9%B1%BC',
      $upstreamCommit,
      $releaseCommit,
      "$installerHash  Sunshine.v4.9.WindowsInstaller.exe",
      "$portableHash  Sunshine.v4.9.Portable-x64.zip"
    )) {
    if (-not $notes.Contains($expected)) { throw "Release notes did not contain: $expected" }
  }
  if ($notes -match '\{\{[A-Z_]+\}\}|204a96826606b3a34cf2cd813aed0f0a9bba7db0|10 月 31 日') {
    throw 'Release notes contain unresolved or stale release-specific metadata.'
  }

  Write-Fixture $upstreamCommitPath '1234567'
  Assert-Rejected { Invoke-GenerateNotes } 'full Git commit SHA'
  Remove-Item -LiteralPath $upstreamCommitPath
  Assert-Rejected { Invoke-GenerateNotes } 'Upstream commit state not found'
  Write-Fixture $upstreamCommitPath $upstreamCommit
  Write-Fixture $upstreamReleasePath "`n"
  Assert-Rejected { Invoke-GenerateNotes } 'Upstream release state is empty'
  Write-Fixture $upstreamReleasePath 'v2027.0101.123456.杂鱼'
  Write-Fixture $checksumsPath '[]'
  Assert-Rejected { Invoke-GenerateNotes } 'exactly one Windows installer'
  Write-Host 'Release notes tests passed: dynamic metadata and invalid state rejection.'
}
finally {
  foreach ($path in @($checksumsPath, $upstreamReleasePath, $upstreamCommitPath, $outputPath)) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
  }
  if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot }
}
