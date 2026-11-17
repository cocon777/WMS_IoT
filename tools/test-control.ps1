$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$compiler = Get-Command g++ -ErrorAction SilentlyContinue
if ($compiler) { $gccPath = $compiler.Source }
else {
    $gccPath = Join-Path $env:USERPROFILE '.platformio/packages/toolchain-gccmingw32/bin/g++.exe'
    if (-not (Test-Path -LiteralPath $gccPath)) {
        throw 'Install g++ or run: .venv\Scripts\python -m platformio pkg install --global --tool platformio/toolchain-gccmingw32'
    }
}
$env:Path = (Split-Path -Parent $gccPath) + ';' + $env:Path
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'tests/results') | Out-Null
$output = Join-Path $projectRoot 'tests/results/control_logic_test.exe'
& $gccPath -std=c++11 (Join-Path $projectRoot 'tests/firmware/control_logic_test.cpp') -o $output
if ($LASTEXITCODE -ne 0) { throw 'Native C++ test build failed' }
& $output
if ($LASTEXITCODE -ne 0) { throw 'Native C++ assertion failed' }
Write-Output 'Native control logic assertions passed'
