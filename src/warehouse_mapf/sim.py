"""Depo simülasyonu. Zaman adım adım ilerler.

Her adımda sırasıyla şunlar olur.
1. Yeni gelen siparişler robotlara atanır.
2. Her robot yolundaki sonraki hücreyi ister. Çakışma varsa robotlardan biri bekler.
3. Robotlar hareket eder. Hedefe varan robot görevin sonraki aşamasına geçer.
4. Birkaç adım ilerleyemeyen robot yolunu yeniden planlar (Local Repair).

Robotlar birbirinin planını bilmez, her biri kendi A*'ını çalıştırır (P0).
Sipariş en yakın boştaki robota verilir.
İlk warmup adımı metriklere katılmaz.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .astar import find_path
from .conflicts import detect_conflicts
from .grid import Cell, Grid
from .orders import Order
from .warehouse import Warehouse

Assigner = Callable[[dict[int, Cell], list[Order]], dict[int, int]]


@dataclass
class Robot:
    id: int
    pos: Cell
    home: Cell
    phase: str = "idle"            # idle | to_pick | to_drop | to_home
    order: Order | None = None
    path: list[Cell] = field(default_factory=list)   # kalan hücreler, şu anki hariç
    blocked_for: int = 0           # art arda ilerleyemediği adım sayısı
    distance: int = 0
    task_waits: int = 0            # sipariş taşırken beklediği adım sayısı

    @property
    def target(self) -> Cell:
        if self.phase == "to_pick":
            return self.order.pick
        if self.phase == "to_drop":
            return self.order.drop
        return self.home


@dataclass
class Metrics:
    steps: int                     # ölçülen adım sayısı (ısınma hariç)
    warmup: int
    robots: int
    orders_arrived: int
    orders_completed: int
    throughput: float              # 100 adımda tamamlanan sipariş
    mean_completion_time: float    # siparişin gelişinden teslimine geçen adım
    mean_distance: float           # robot başına toplam adım
    mean_wait_per_order: float     # tamamlanan sipariş başına bekleme adımı
    conflicts: int                 # tespit edilen çakışma sayısı
    repairs: int                   # Local Repair ile yeniden planlama sayısı


class Simulation:
    def __init__(self, warehouse: Warehouse, orders: list[Order], n_robots: int,
                 assign: Assigner, horizon: int = 1000, repair_after: int = 3,
                 warmup: int = 0):
        if n_robots > len(warehouse.park_cells):
            raise ValueError(f"En fazla {len(warehouse.park_cells)} robot sığar")
        self.warehouse = warehouse
        self.grid = warehouse.grid
        self.orders = sorted(orders, key=lambda o: o.arrival)
        self.assign = assign
        self.horizon = horizon
        self.warmup = warmup
        self.repair_after = repair_after

        # robotları park yerlerine eşit aralıklarla diz
        parks = warehouse.park_cells
        homes = [parks[i * len(parks) // n_robots] for i in range(n_robots)]
        self.robots = [Robot(i, h, h) for i, h in enumerate(homes)]

        self.t = 0
        self._next_order = 0
        self.open_orders: list[Order] = []
        self.completion_times: list[int] = []
        self.task_waits_done = 0
        self.conflicts = 0
        self.repairs = 0
        self._baseline: dict | None = None   # ısınma bitiminde sayaçların değeri

    def plan(self, robot: Robot, avoid: set[Cell] | None = None) -> None:
        grid = self.grid
        if avoid:
            grid = Grid(grid.width, grid.height, grid.blocked | (avoid - {robot.target}))
        path = find_path(grid, robot.pos, robot.target)
        robot.path = path[1:] if path else []

    def step(self) -> None:
        self._release_orders()
        self._assign_orders()

        current = {r.id: r.pos for r in self.robots}
        intended = {r.id: (r.path[0] if r.path else r.pos) for r in self.robots}

        conflicts = detect_conflicts(current, intended)
        self.conflicts += len(conflicts)
        while conflicts:
            for c in conflicts:
                a, b = c.robots
                if intended[a] == current[a]:
                    loser = b                  # a zaten duruyor, hareket eden b bekler
                elif intended[b] == current[b]:
                    loser = a
                else:
                    loser = b                  # ikisi de hareket ediyorsa id'si büyük olan bekler
                intended[loser] = current[loser]
            conflicts = detect_conflicts(current, intended)

        for r in self.robots:
            if intended[r.id] != r.pos:
                r.pos = intended[r.id]
                r.path.pop(0)
                r.distance += 1
                r.blocked_for = 0
            elif r.path:
                # çakışma yüzünden plandaki hücreye gidemedi
                r.blocked_for += 1
                if r.phase in ("to_pick", "to_drop"):
                    r.task_waits += 1

        for r in self.robots:
            self._advance(r)

        occupied = {r.pos for r in self.robots}
        for r in self.robots:
            if r.blocked_for >= self.repair_after:
                self.plan(r, avoid=occupied - {r.pos})
                r.blocked_for = 0
                self.repairs += 1

        self.t += 1

    def _release_orders(self) -> None:
        while self._next_order < len(self.orders) and self.orders[self._next_order].arrival <= self.t:
            self.open_orders.append(self.orders[self._next_order])
            self._next_order += 1

    def _assign_orders(self) -> None:
        if not self.open_orders:
            return
        available = {r.id: r.pos for r in self.robots if r.phase in ("idle", "to_home")}
        if not available:
            return
        assignment = self.assign(available, list(self.open_orders))
        by_id = {o.id: o for o in self.open_orders}
        for order_id, robot_id in assignment.items():
            robot = self.robots[robot_id]
            robot.order = by_id[order_id]
            robot.phase = "to_pick"
            self.plan(robot)
            self.open_orders.remove(robot.order)

    def _advance(self, r: Robot) -> None:
        """Hedefine varan robotu görevinin sonraki aşamasına geçirir."""
        if r.pos != r.target:
            if not r.path and r.phase != "idle":
                self.plan(r)           # yolu yok, tekrar dene
            return
        if r.phase == "to_pick":
            r.phase = "to_drop"
            self.plan(r)
        elif r.phase == "to_drop":
            self.completion_times.append(self.t + 1 - r.order.arrival)
            self.task_waits_done += r.task_waits
            r.task_waits = 0
            r.order = None
            r.phase = "to_home"
            self.plan(r)
        elif r.phase == "to_home":
            r.phase = "idle"

    def _counters(self) -> dict:
        return {
            "completed": len(self.completion_times),
            "arrived": self._next_order,
            "distance": sum(r.distance for r in self.robots),
            "waits": self.task_waits_done,
            "conflicts": self.conflicts,
            "repairs": self.repairs,
        }

    def run(self) -> Metrics:
        total = self.warmup + self.horizon
        while self.t < total:
            if self.t == self.warmup:
                self._baseline = self._counters()
            self.step()
        start, end = self._baseline, self._counters()
        times = self.completion_times[start["completed"]:]
        done = len(times)
        return Metrics(
            steps=self.horizon,
            warmup=self.warmup,
            robots=len(self.robots),
            orders_arrived=end["arrived"] - start["arrived"],
            orders_completed=done,
            throughput=100 * done / self.horizon,
            mean_completion_time=sum(times) / done if done else float("nan"),
            mean_distance=(end["distance"] - start["distance"]) / len(self.robots),
            mean_wait_per_order=(end["waits"] - start["waits"]) / done if done else float("nan"),
            conflicts=end["conflicts"] - start["conflicts"],
            repairs=end["repairs"] - start["repairs"],
        )
