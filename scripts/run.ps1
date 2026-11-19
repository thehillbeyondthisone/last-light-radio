[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet('demo', 'test', 'check', 'probe', 'workflow', 'render', 'job', 'studio', 'quickstart', 'clip-editor')]
    [string]$Action = 'demo',
    [string]$Python = $env:LLR_PYTHON,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)
$ErrorActionPreference = 'Stop'
$pythonArguments = @()
if (-not $Python) {
    $venv = Join-Path (Split-Path -Parent $PSScriptRoot) '.local\venv\Scripts\python.exe'
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    $interpreter = Get-Command python.exe -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $venv) {
        $Python = $venv
    } elseif ($launcher) {
        $Python = $launcher.Source
        $pythonArguments = @('-3')
    } elseif ($interpreter -and $interpreter.Source -notlike '*WindowsApps*') {
        $Python = $interpreter.Source
    } else {
        $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $bundled) { $Python = $bundled }
    }
}
if (-not $Python) { throw 'Python 3.11+ is required. Set LLR_PYTHON or pass -Python with its executable path.' }
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    & $Python @pythonArguments -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required. Set LLR_PYTHON to a supported python.exe.' }
    switch ($Action) {
        'quickstart' { & $Python @pythonArguments scripts/quickstart.py @ExtraArgs }
        'test' { & $Python @pythonArguments -m unittest discover -s tests -v @ExtraArgs }
        'check' { & $Python @pythonArguments scripts/check.py @ExtraArgs }
        default { & $Python @pythonArguments -m last_light_radio $Action @ExtraArgs }
    }
    $result = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $result
