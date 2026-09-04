param([string]$StoragePath = "E:\VectorTradingData")
$resolved = [System.IO.Path]::GetFullPath($StoragePath)
if ([System.IO.Path]::GetPathRoot($resolved) -eq $resolved) { throw "Choose a subdirectory, not a drive root." }
New-Item -ItemType Directory -Force -Path $resolved | Out-Null
@("postgres","redis","app","app\logs","app\models","app\knowledge","backups") | ForEach-Object { New-Item -ItemType Directory -Force -Path (Join-Path $resolved $_) | Out-Null }
Write-Host "HDD storage prepared at $resolved"

