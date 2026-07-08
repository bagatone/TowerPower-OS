from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from .stock_alarm import StockAlarm


class RowGenerator:
    def build_operational_actions(
        self,
        alarms: list[StockAlarm],
        problems: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        now = datetime.now().isoformat(timespec="seconds")

        for alarm in alarms:
            actions.append(
                {
                    "created_at": now,
                    "source": "STOCK",
                    "priority": alarm.priority,
                    "action": (
                        f"Verificare disponibilità per {alarm.item}: "
                        f"DISPONIBILE {alarm.disponibile} < PRENOTATO {alarm.prenotato}."
                    ),
                    "dry_run": True,
                    "payload": asdict(alarm),
                }
            )

        for problem in problems:
            if not any(str(value).strip() for value in problem.values()):
                continue
            status = problem.get("STATO") or problem.get("STATUS") or ""
            if status.upper() not in {"CHIUSO", "RISOLTO", "CLOSED", "DONE"}:
                actions.append(
                    {
                        "created_at": now,
                        "source": "PROBLEMI",
                        "priority": problem.get("PRIORITA")
                        or problem.get("PRIORITÀ")
                        or problem.get("GRAVITÀ")
                        or "DA VALUTARE",
                        "action": problem.get("AZIONE")
                        or problem.get("AZIONE_RICHIESTA")
                        or problem.get("DESCRIZIONE")
                        or problem.get("PROBLEMA")
                        or "Problema aperto da verificare.",
                        "dry_run": True,
                        "payload": problem,
                    }
                )

        return actions
