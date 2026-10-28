"""Robot ürünü raftan alınca hangi paketleme istasyonuna gideceğini seçer.

NearestStation en yakın istasyonu seçer. QueueAwareStation, mesafe + alpha * (benden önce varacak
robot sayısı) değeri en küçük olan istasyonu seçer. LearnedStation her istasyon için teslimat
süresini tahmin eder ve en kısasını seçer. Tahmin, ikinci dereceden özelliklerle ridge regresyonla yapılır.

Simulation'da station=None ise siparişte yazan istasyon kullanılır.
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .grid import Cell

if TYPE_CHECKING:
    from .sim import Robot, Simulation

CROWD_RADIUS = 3


def station_features(sim: Simulation, robot: Robot) -> list[list[float]]:
    """Her istasyon için [mesafe, benden önce varacak robot, o istasyona giden robot, kalabalık]."""
    here = robot.pos
    rows = []
    for drop in sim.warehouse.drop_cells:
        d = sim.dist(here, drop)
        inbound = ahead = crowd = 0
        for other in sim.robots:
            if other.id == robot.id:
                continue
            if other.phase == "to_drop" and other.order is not None and other.order.drop == drop:
                inbound += 1
                if sim.dist(other.pos, drop) < d:
                    ahead += 1
            if abs(other.pos[0] - drop[0]) + abs(other.pos[1] - drop[1]) <= CROWD_RADIUS:
                crowd += 1
        rows.append([float(d), float(ahead), float(inbound), float(crowd)])
    return rows


def _route(sim: Simulation, start: Cell, goal: Cell) -> list[Cell]:
    """Mesafesi azalan komşuya adım adım giderek en kısa yolu çıkarır (robotlar yok sayılır)."""
    path, cell = [], start
    d = sim.dist(cell, goal)
    while cell != goal and d < 10**6:
        nxt = min(sim.grid.neighbors(cell), key=lambda n: sim.dist(n, goal), default=None)
        if nxt is None or sim.dist(nxt, goal) >= d:
            break
        cell, d = nxt, sim.dist(nxt, goal)
        path.append(cell)
    return path


def station_features_v2(sim: Simulation, robot: Robot) -> list[list[float]]:
    """station_features + [istasyona giden yoldaki robot sayısı, bekleyen sipariş / 10]."""
    occupied = {r.pos for r in sim.robots if r.id != robot.id}
    load = len(sim.open_orders) / 10.0
    rows = station_features(sim, robot)
    for row, drop in zip(rows, sim.warehouse.drop_cells):
        on_route = sum(1 for c in _route(sim, robot.pos, drop) if c in occupied)
        row.extend([float(on_route), load])
    return rows


class NearestStation:
    name = "nearest"

    def choose(self, sim: Simulation, robot: Robot) -> int:
        feats = station_features(sim, robot)
        return min(range(len(feats)), key=lambda i: (feats[i][0], i))

    def on_delivery(self, robot_id: int, t: int) -> None:
        pass


class QueueAwareStation:
    """Benden önce varacak her robot alpha adım gecikme sayılır."""
    name = "queue-aware"

    def __init__(self, alpha: float = 4.0):
        self.alpha = alpha

    def choose(self, sim: Simulation, robot: Robot) -> int:
        feats = station_features(sim, robot)
        return min(range(len(feats)), key=lambda i: (feats[i][0] + self.alpha * feats[i][1], i))

    def on_delivery(self, robot_id: int, t: int) -> None:
        pass


def _poly(f: list[float]) -> np.ndarray:
    """İkinci dereceden özellikleri, yani [1, x, x_i * x_j] vektörünü döndürür."""
    x = np.asarray(f, dtype=float)
    pairs = [x[i] * x[j] for i in range(len(x)) for j in range(i, len(x))]
    return np.concatenate(([1.0], x, pairs))


class LearnedStation:
    """Öğrenen istasyon seçici (contextual bandit).

    Her istasyon için teslimat süresini tahmin edip en kısasını seçer. Eğitimde epsilon
    olasılıkla rastgele istasyon seçer. Gerçekleşen süreler fit() için saklanır.
    """
    name = "learned"

    def __init__(self, epsilon: float = 0.0, seed: int = 0, ridge: float = 1.0,
                 extended: bool = False, maximize: bool = False):
        self.extended = extended          # station_features_v2 kullanılsın mı
        self.maximize = maximize          # True ise rollout değeri en büyük olan, False ise süresi en kısa olan seçilir
        self.epsilon = epsilon
        self.rng = random.Random(seed)
        self.ridge = ridge
        self.weights: np.ndarray | None = None
        self.mean: np.ndarray | None = None      # standardizasyon için ortalama ve std
        self.std: np.ndarray | None = None
        self.X: list[np.ndarray] = []              # seçilen istasyonun özellikleri
        self.y: list[float] = []                   # gerçekleşen teslimat süresi
        self._pending: dict[int, tuple[np.ndarray, int]] = {}

    def features(self, sim: Simulation, robot: Robot) -> list[list[float]]:
        return station_features_v2(sim, robot) if self.extended else station_features(sim, robot)

    def predict(self, feats: list[list[float]]) -> np.ndarray:
        X = np.array([_poly(f) for f in feats])
        if self.weights is None:
            return -X[:, 1] if self.maximize else X[:, 1]    # model yoksa sadece mesafeye bak
        return ((X - self.mean) / self.std) @ self.weights

    def choose(self, sim: Simulation, robot: Robot) -> int:
        feats = self.features(sim, robot)
        if self.rng.random() < self.epsilon:
            i = self.rng.randrange(len(feats))
        else:
            pred = self.predict(feats)
            i = int(np.argmax(pred) if self.maximize else np.argmin(pred))
        self._pending[robot.id] = (_poly(feats[i]), sim.t)
        return i

    def on_delivery(self, robot_id: int, t: int) -> None:
        if robot_id in self._pending:
            x, t0 = self._pending.pop(robot_id)
            self.X.append(x)
            self.y.append(float(t - t0))

    def fit(self) -> None:
        """Toplanan verilere ridge regresyon uydurur."""
        X, y = np.array(self.X), np.array(self.y)
        self.mean = X.mean(axis=0)
        self.std = X.std(axis=0)
        self.mean[0], self.std[0] = 0.0, 1.0       # sabit terim standardize edilmez
        self.std[self.std == 0] = 1.0
        Z = (X - self.mean) / self.std
        A = Z.T @ Z + self.ridge * np.eye(Z.shape[1])
        A[0, 0] -= self.ridge                       # sabit terim cezalandırılmaz
        self.weights = np.linalg.solve(A, Z.T @ y)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"weights": self.weights.tolist(), "mean": self.mean.tolist(),
                                    "std": self.std.tolist(), "samples": len(self.y),
                                    "extended": self.extended, "maximize": self.maximize}, indent=1))

    @classmethod
    def load(cls, path: Path) -> LearnedStation:
        data = json.loads(path.read_text())
        agent = cls(epsilon=0.0, extended=data.get("extended", False), maximize=data.get("maximize", False))
        agent.weights = np.array(data["weights"])
        agent.mean = np.array(data["mean"])
        agent.std = np.array(data["std"])
        return agent


def drop_cell(sim: Simulation, index: int) -> Cell:
    return sim.warehouse.drop_cells[index]


class RolloutLabeler:
    """Rollout ile eğitim verisi toplar.

    1. Kararları kural verir, epsilon olasılıkla rastgele istasyon seçilir.
    2. Kararların bir kısmında simülasyon her istasyon için kopyalanır, horizon adım ilerletilir.
    3. Etiket = bu sürede yapılan teslimat sayısı - 0.02 * teslimata giden robotların kalan yolu.

    Kopyaların hepsi aynı durumdan başladığı için aradaki fark sadece bu karardan gelir.
    """
    name = "rollout-labeler"

    def __init__(self, alpha: float = 2.0, epsilon: float = 0.1, sample: float = 0.25,
                 horizon: int = 60, seed: int = 0):
        self.rule = QueueAwareStation(alpha)
        self.epsilon = epsilon
        self.sample = sample
        self.horizon = horizon
        self.rng = random.Random(seed)
        self.X: list[np.ndarray] = []
        self.y: list[float] = []
        self._pending: list[tuple[int, list[list[float]]]] = []

    def choose(self, sim: Simulation, robot: Robot) -> int:
        if self.rng.random() < self.sample:
            self._pending.append((robot.id, station_features_v2(sim, robot)))
        if self.rng.random() < self.epsilon:
            return self.rng.randrange(len(sim.warehouse.drop_cells))
        return self.rule.choose(sim, robot)

    def on_delivery(self, robot_id: int, t: int) -> None:
        pass

    def after_step(self, sim: Simulation) -> None:
        pending, self._pending = self._pending, []
        for robot_id, feats in pending:
            values = self._rollouts(sim, robot_id)
            if values is None:
                continue
            for f, v in zip(feats, values):
                self.X.append(_poly(f))
                self.y.append(v)

    def _rollouts(self, sim: Simulation, robot_id: int) -> list[float] | None:
        robot = sim.robots[robot_id]
        if robot.phase != "to_drop" or robot.order is None:
            return None
        shared = {id(x): x for x in (sim.warehouse, sim.static_grid, sim.grid, sim.dist, sim.orders)}
        shared[id(self)] = None
        base_station, sim.station = sim.station, self.rule      # kopyalarda kural karar verir
        values = []
        for drop in sim.warehouse.drop_cells:
            clone = copy.deepcopy(sim, dict(shared))
            r = clone.robots[robot_id]
            r.order = replace(r.order, drop=drop)
            clone._now = clone.t
            clone.plan(r)
            before = len(clone.completion_steps)
            for _ in range(self.horizon):
                clone.step()
            delivered = len(clone.completion_steps) - before
            remaining = sum(clone.dist(x.pos, x.order.drop) for x in clone.robots
                            if x.phase == "to_drop" and x.order is not None)
            values.append(delivered - 0.02 * remaining)
        sim.station = base_station
        return values
