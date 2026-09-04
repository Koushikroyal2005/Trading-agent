#!/usr/bin/env bash
set -euo pipefail
[[ -f .env ]] || { cp .env.example .env; echo "Created .env; set POSTGRES_PASSWORD and REDIS_PASSWORD."; exit 1; }
docker compose --env-file .env -f docker-compose.yml up -d --build
