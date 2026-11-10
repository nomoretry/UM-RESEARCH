# Lightweight Windows entry point; arguments are forwarded without shell evaluation.
# Example: .\scripts\records.ps1 status --conversation 0001
$ErrorActionPreference = 'Stop'
$scriptFile = Join-Path $PSScriptRoot 'conversation_records.py'
& python -X utf8 $scriptFile @args
exit $LASTEXITCODE
