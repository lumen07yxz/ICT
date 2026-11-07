$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$distRoot = Join-Path $PSScriptRoot 'dist\workflow-app'
$workRoot = Join-Path $PSScriptRoot 'build\workflow-app-production'
$spec = Join-Path $PSScriptRoot 'ICTWorkflowWorkbench.spec'
$exePath = Join-Path $distRoot 'ICTWorkflowWorkbench.exe'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "项目打包环境不存在：$python"
}

Push-Location $frontendRoot
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) {
        throw "前端生产构建失败，退出码：$LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$buildStartedAt = Get-Date
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
& $python -m PyInstaller --noconfirm --distpath $distRoot --workpath $workRoot $spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 打包失败，退出码：$LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "打包命令完成但没有生成桌面程序：$exePath"
}
if ((Get-Item -LiteralPath $exePath).LastWriteTime -lt $buildStartedAt) {
    throw "目标程序的时间戳未更新，拒绝把旧产物当成本次构建结果：$exePath"
}

Get-Item -LiteralPath $exePath | Select-Object FullName, Length, LastWriteTime
Get-FileHash -LiteralPath $exePath -Algorithm SHA256 | Select-Object Algorithm, Hash, Path
