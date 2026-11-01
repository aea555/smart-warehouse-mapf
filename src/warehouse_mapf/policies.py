"""Deneylerde karşılaştırılan politikalar.

P0'da her robot kendi A*'ını kullanır, takılınca Local Repair ile yeniden planlar.
P1'de yollar WHCA* ile planlanır (pencere 16, 8 adımda bir yeniden planlama).
P2, P1'e açık artırmayla atamayı ve olay olunca hemen yeniden planlamayı ekler.
P3-rule, P2'ye kural tabanlı istasyon seçimini ekler ve ürünü taşıyan robotu önce planlar.
P3, P2'ye öğrenen istasyon seçiciyi ve öğrenilmiş planlama sırasını ekler.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .priority import LinearPriority, heuristic
from .stations import LearnedStation, QueueAwareStation

MODELS = Path(__file__).resolve().parents[2] / "models"
POLICIES = ["P0", "P1", "P2", "P3-rule", "P3"]


def policy_options(policy: str, models: Path = MODELS) -> dict:
    """Politikanın Simulation'a verilecek ayarları. Her çağrıda yeni nesneler döner."""
    if policy == "P0":
        return {}
    if policy == "P1":
        return {"planner": "windowed"}
    p2 = {"planner": "windowed", "allocation": "auction", "event_replan": True}
    if policy == "P2":
        return p2
    if policy == "P3-rule":
        alpha = json.loads((models / "station_rule.json").read_text())["alpha"]
        return {**p2, "station": QueueAwareStation(alpha), "priority": heuristic("carrying-first")}
    if policy == "P3":
        data = json.loads((models / "priority_policy.json").read_text())
        priority = LinearPriority(np.array(data["weights"]) / np.array(data["scale"]), name="learned")
        return {**p2, "station": LearnedStation.load(models / "station_policy.json"), "priority": priority}
    raise ValueError(f"bilinmeyen politika: {policy}")
