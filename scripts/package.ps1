# RPA Helper 打包脚本：PyInstaller + 内嵌 Chromium。
# Author: huaiqing.wang

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# 安装精简版打包依赖（不含 OCR / PaddlePaddle）。
Write-Host "Installing slim packaging requirements..."
py -m pip install -r requirements-packaging.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 防止已运行的 exe 占用 dist/ 文件。
Get-Process RPAHelper -ErrorAction SilentlyContinue | Stop-Process -Force

# 清理旧构建产物，避免 hiddenimports 残留。
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# 主构建步骤：生成 dist/RPAHelper/。
py -m PyInstaller --noconfirm RPAHelper.spec
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 在 exe 同级目录预创建运行时目录（用户首次运行也能直接看到）。
$BuildDir = Join-Path $ProjectRoot "dist/RPAHelper"
New-Item -ItemType Directory -Force -Path "$BuildDir/config", "$BuildDir/logs" | Out-Null

# 把 Playwright 的 Chromium 一并打入 _internal/playwright/...
& "$PSScriptRoot/_bundle_chromium.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 删除占空间的 headless shell（GUI 模式用不到）。
& "$PSScriptRoot/_slim_build.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Build complete: $BuildDir/RPAHelper.exe"
