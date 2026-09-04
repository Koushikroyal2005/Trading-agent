param([string]$Destination = ".\data\backups")
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
docker compose --env-file .env -f docker-compose.yml exec -T timescaledb pg_dump -U vector -Fc vector | Set-Content -Encoding Byte (Join-Path $Destination "vector-$stamp.dump")
