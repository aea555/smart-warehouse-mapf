"""WHCA*'ta robotların hangi sırayla planlanacağı.

Varsayılan sıra rastgele. Burada her robota bir puan veriliyor ve puanı büyük olan önce
planlanıyor. Puan, ağırlıklarla robotun özelliklerinin çarpımlarının toplamı.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .sim import Robot, Simulation

# carrying (ürünü taşıyor mu, 0/1), on_task (görevde mi, 0/1), dist (hedefe mesafe),
# waited (bu siparişte kaç adım bekledi), blocked (art arda kaç adım takıldı),
# crowd (2 hücre yakınındaki robot sayısı), age (siparişin yaşı / 10)
FEATURES = ["carrying", "on_task", "dist", "waited", "blocked", "crowd", "age"]


def robot_features(sim: Simulation, r: Robot) -> list[float]:
    on_task = r.phase in ("to_pick", "to_drop")
    crowd = sum(1 for o in sim.robots
                if o.id != r.id and abs(o.pos[0] - r.pos[0]) + abs(o.pos[1] - r.pos[1]) <= 2)
    age = (sim.t - r.order.arrival) / 10.0 if (on_task and r.order is not None) else 0.0
    return [float(r.phase == "to_drop"), float(on_task), float(sim.dist(r.pos, r.target)),
            float(r.task_waits), float(r.blocked_for), float(crowd), age]


class RandomPriority:
    name = "random"

    def order(self, sim: Simulation) -> list[Robot]:
        robots = list(sim.robots)
        sim.rng.shuffle(robots)
        return robots


class LinearPriority:
    """Robotları puana göre büyükten küçüğe sıralar. Puanı eşit olanların sırası rastgele."""

    def __init__(self, weights, name: str = "linear"):
        self.weights = np.asarray(weights, dtype=float)
        self.name = name

    def order(self, sim: Simulation) -> list[Robot]:
        robots = list(sim.robots)
        sim.rng.shuffle(robots)                      # sorted kararlı, eşitler bu karışık sırada kalır
        scores = {r.id: float(self.weights @ np.asarray(robot_features(sim, r))) for r in robots}
        return sorted(robots, key=lambda r: -scores[r.id])


def heuristic(name: str) -> LinearPriority:
    """Kural tabanlı sıralamalar. Her kural bir ağırlık vektörü olarak yazıldı."""
    w = {
        "far-first":      [0, 10, 1, 0, 0, 0, 0],      # görevdekiler önce, aralarında hedefi uzak olan önce
        "near-first":     [0, 10, -1, 0, 0, 0, 0],
        "carrying-first": [100, 10, 1, 0, 0, 0, 0],    # ürün taşıyan önce, sonra uzak olan
        "waited-first":   [0, 10, 0, 1, 2, 0, 0],      # en çok bekleyen önce
        "oldest-first":   [0, 10, 0, 0, 0, 0, 1],      # en eski sipariş önce
    }[name]
    return LinearPriority(w, name=name)
