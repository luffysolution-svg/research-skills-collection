[CmdletBinding()]
param(
    [switch]$Json,
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'document-tools-doctor.py'
$python = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $python) {
    throw 'Python 3 is required to run document-tools-doctor.py'
}

$arguments = @($scriptPath)
if ($Json) { $arguments += '--json' }
if ($Strict) { $arguments += '--strict' }

& $python.Source @arguments
exit $LASTEXITCODE
