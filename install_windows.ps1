$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCmd = $null
$pythonArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = 'py'
    $pythonArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = 'python'
    $pythonArgs = @()
}

Write-Host 'Claude Desktop 中文补丁（Windows / PowerShell）'
Write-Host "目录: $scriptDir"
Write-Host ''

if (-not $pythonCmd) {
    Write-Host '未找到 Python 3。' -ForegroundColor Red
    Write-Host '请先安装 Python 3，并确保以下任一命令可用：'
    Write-Host '  1. py -3'
    Write-Host '  2. python'
    Write-Host ''
    Write-Host '如果你只是被 PowerShell 执行策略拦住，也可以手动执行：'
    Write-Host '  powershell -ExecutionPolicy Bypass -File .\install_windows.ps1'
    Write-Host ''
    Read-Host '按回车退出'
    exit 1
}

Push-Location $scriptDir
try {
    & $pythonCmd @pythonArgs 'patch_claude_zh_cn.py' '--launch' @args
    $status = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ''
if ($status -ne 0) {
    Write-Host "安装失败，错误码: $status" -ForegroundColor Red
} else {
    Write-Host '安装完成。' -ForegroundColor Green
}
Write-Host ''
Read-Host '按回车退出'
exit $status
