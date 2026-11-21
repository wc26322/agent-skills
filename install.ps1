<#
    把本仓库 skills/ 下的技能安装到 WorkBuddy 用户级技能目录。

    用法:
        .\install.ps1                        装到 %USERPROFILE%\.workbuddy\skills
        .\install.ps1 -Dest "D:\my\skills"   装到指定目录

    注意: 覆盖安装时不会动目标目录下的 vault/，那里是本机的断言保管区。
#>
param(
    [string]$Dest = (Join-Path $env:USERPROFILE ".workbuddy\skills")
)

$ErrorActionPreference = "Stop"

$src = Join-Path $PSScriptRoot "skills"
if (-not (Test-Path $src)) {
    Write-Host "找不到 skills 目录: $src"
    exit 1
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null

$count = 0
Get-ChildItem -Path $src -Directory | ForEach-Object {
    $name = $_.Name
    $target = Join-Path $Dest $name
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    # 逐个复制顶层项，跳过 vault —— 覆盖安装不能把本机运行数据一起抹掉
    Get-ChildItem -Path $_.FullName |
        Where-Object { $_.Name -ne "vault" } |
        ForEach-Object {
            Copy-Item -Path $_.FullName -Destination (Join-Path $target $_.Name) -Recurse -Force
        }

    Write-Host ("已安装 {0}  ->  {1}" -f $name, $target)
    $count++
}

Write-Host ""
Write-Host ("完成，共 {0} 个技能。开新会话后生效。" -f $count)
