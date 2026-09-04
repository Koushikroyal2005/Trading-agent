"""Durable, atomic system state used by safety controls."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SystemMemento:
    created_at: str
    cycles: int = 0
    selected_strategy: str = "auto"
    auto_trade: bool = False
    emergency_stopped: bool = False
    learned_closed_trades: int = 0


class SystemStateCaretaker:
    def __init__(self, path: Path):
        self.path = path / "state" / "system.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, cycles: int, selected_strategy: str, auto_trade: bool, emergency_stopped: bool, learned_closed_trades: int = 0) -> SystemMemento:
        state = SystemMemento(datetime.now(timezone.utc).isoformat(), cycles, selected_strategy, auto_trade, emergency_stopped, learned_closed_trades)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return state

    def restore(self) -> SystemMemento | None:
        if not self.path.exists():
            return None
        values = json.loads(self.path.read_text(encoding="utf-8"))
        return SystemMemento(**values)
