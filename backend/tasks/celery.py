"""Celery worker and Beat schedules that invoke the API-owned orchestrator."""
from __future__ import annotations

import os

import httpx
from celery import Celery
from redis import Redis

from backend.utils.config import get_settings

settings = get_settings()
celery_app = Celery("vector", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"], worker_concurrency=2, task_time_limit=120, broker_connection_retry_on_startup=True, timezone="UTC")

api_base = os.getenv("INTERNAL_API_URL", "http://api:8000")
headers = {"X-API-Key": settings.api_key.get_secret_value()} if settings.api_key else {}


def _post(path: str, payload: dict | None = None) -> dict:
    with httpx.Client(timeout=110) as client:
        response = client.post(f"{api_base}{path}", headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


@celery_app.task(name="trading.run_cycle", autoretry_for=(httpx.HTTPError,), retry_backoff=True, max_retries=3)
def run_cycle(symbol: str = "AAPL", timeframe: int = 15):
    lock_name = f"vector:lock:cycle:{symbol}:{timeframe}"
    redis = Redis.from_url(settings.redis_url)
    with redis.lock(lock_name, timeout=115, blocking_timeout=1):
        return _post("/api/v1/orchestrator/scheduled-run", {"symbol": symbol, "timeframe": timeframe})


@celery_app.task(name="trading.reconcile", autoretry_for=(httpx.HTTPError,), retry_backoff=True, max_retries=3)
def reconcile():
    return _post("/api/v1/orchestrator/reconcile")


beat_schedule = {
    f"cycle-{symbol.lower()}-{timeframe}m": {"task": "trading.run_cycle", "schedule": settings.cycle_schedule_seconds, "args": (symbol, timeframe)}
    for symbol in settings.symbols for timeframe in settings.timeframes
}
beat_schedule["broker-reconciliation"] = {"task": "trading.reconcile", "schedule": 60.0}
celery_app.conf.beat_schedule = beat_schedule
