if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created .env. Set POSTGRES_PASSWORD and REDIS_PASSWORD before Docker startup." }
docker compose --env-file .env -f docker-compose.yml up -d --build
