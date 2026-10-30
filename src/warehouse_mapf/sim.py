"""Depo simülasyonu. Zaman adım adım ilerler.

Her adımda sırasıyla şunlar olur.
1. Yeni gelen siparişler robotlara atanır.
2. Her robot yolundaki sonraki hücreyi ister. Çakışma varsa robotlardan biri bekler.
3. Robotlar hareket eder. Hedefe varan robot görevin sonraki aşamasına geçer.
4. Birkaç adım ilerleyemeyen robot yolunu yeniden planlar (Local Repair).

planner olarak independent (P0), cooperative (CA*) ya da windowed (WHCA*) seçilebilir.
allocation olarak greedy (en yakın boştaki robot) ya da auction (açık artırma) seçilebilir.
Simülasyona koridor kapanması ve robot arızası olayları da eklenebilir.
İlk warmup adımı metriklere katılmaz. stall_window adım boyunca hiç teslimat olmazsa
tıkanma sayılır.
"""

from __future__ import annotations

import heapq
import random
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .astar import find_path, manhattan, reconstruct_path
from .auction import Bidder, auction
from .conflicts import detect_conflicts
from .cooperative import DistanceMap, ReservationTable, plan_cooperative, plan_windowed
from .grid import Cell, Grid
from .orders import Order
from .warehouse import Warehouse

Assigner = Callable[[dict[int, Cell], list[Order]], dict[int, int]]


@dataclass(frozen=True)
class Event:
    kind: str                          # "block" ya da "fail"
    start: int
    duration: int
    cells: tuple[Cell, ...] = ()       # block olayında kapanan hücreler
    count: int = 0                     # fail olayında arızalanacak robot sayısı (o an görevde olanlardan rastgele seçilir)


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
    agitation: int = 0             # Local Repair'de yol aramasına eklenen gürültü miktarı
    next_order: Order | None = None    # açık artırmada kazanılmış sıradaki iş
    failed_until: int = -1             # bu adıma kadar arızalı

    def failed(self, t: int) -> bool:
        return t < self.failed_until

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
    stalls: int                    # tıkanma sayısı (stall_window adım hiç teslimat yok)
    stalls_resolved: int           # kendiliğinden çözülen tıkanma sayısı
    deadlocked: int                # simülasyon tıkanmış halde bittiyse 1


class Simulation:
    def __init__(self, warehouse: Warehouse, orders: list[Order], n_robots: int,
                 assign: Assigner, horizon: int = 1000, repair_after: int = 3,
                 warmup: int = 0, agitation: bool = True, seed: int = 0,
                 stall_window: int = 200, planner: str = "independent",
                 window: int = 16, replan_every: int = 8,
                 allocation: str = "greedy", reauction_every: int = 10,
                 events: tuple[Event, ...] = (), event_replan: bool = False,
                 station=None, priority=None):
        if n_robots > len(warehouse.park_cells):
            raise ValueError(f"En fazla {len(warehouse.park_cells)} robot sığar")
        self.warehouse = warehouse
        self.grid = warehouse.grid
        self.orders = sorted(orders, key=lambda o: o.arrival)
        self.assign = assign
        self.horizon = horizon
        self.warmup = warmup
        self.repair_after = repair_after
        self.use_agitation = agitation
        self.rng = random.Random(seed)
        self.stall_window = stall_window
        if planner not in ("independent", "cooperative", "windowed"):
            raise ValueError(f"Bilinmeyen planlayıcı: {planner}")
        self.planner = planner
        self.cooperative = planner in ("cooperative", "windowed")   # rezervasyon tablosu kullanılıyor mu
        self.window = window
        self.replan_every = replan_every
        if allocation not in ("greedy", "auction"):
            raise ValueError(f"Bilinmeyen atama: {allocation}")
        self.allocation = allocation
        self.reauction_every = reauction_every
        self.events = sorted(events, key=lambda e: e.start)
        self.event_replan = event_replan
        self.station = station          # paketleme istasyonu seçici (stations.py), None ise siparişteki istasyon kullanılır
        self.priority = priority        # WHCA* öncelik sırası (priority.py), None ise rastgele
        self.event_rng = random.Random(seed + 7919)   # arızalanacak robotların seçimi
        self.static_grid = warehouse.grid
        self.temp_blocked: set[Cell] = set()
        self.dist = DistanceMap(self.grid)

        # robotları park yerlerine eşit aralıklarla diz
        parks = warehouse.park_cells
        homes = [parks[i * len(parks) // n_robots] for i in range(n_robots)]
        self.robots = [Robot(i, h, h) for i, h in enumerate(homes)]

        self.table = ReservationTable()
        if self.planner == "cooperative":
            for r in self.robots:
                self.table.hold(r.id, r.pos, 0)    # boştaki robot park yerini süresiz tutar

        self.t = 0
        self._now = 0          # robotların şu anki konumlarının ait olduğu zaman adımı
        self._next_order = 0
        self.open_orders: list[Order] = []
        self.completion_times: list[int] = []
        self.completion_steps: list[int] = []       # her teslimatın yapıldığı adım (zaman serisi için)
        self.task_waits_done = 0
        self.conflicts = 0
        self.repairs = 0
        self._baseline: dict | None = None   # ısınma bitiminde sayaçların değeri
        self._last_completion = 0
        self.stalls = 0
        self.stalls_resolved = 0
        self.in_stall = False

    def plan(self, robot: Robot, avoid: set[Cell] | None = None) -> None:
        if robot.failed(self._now):
            self._hold_failed(robot)
            return
        if self.planner == "windowed":
            self._plan_windowed(robot)
            return
        if self.cooperative:
            self._plan_cooperative(robot)
            return
        grid = self.grid
        if avoid:
            grid = Grid(grid.width, grid.height, grid.blocked | (avoid - {robot.target}))
        if self.use_agitation and robot.agitation > 0:
            path = self._noisy_path(grid, robot.pos, robot.target, noise=robot.agitation)
        else:
            path = find_path(grid, robot.pos, robot.target)
        robot.path = path[1:] if path else []

    def _hold_failed(self, robot: Robot) -> None:
        """Arızalı robot yerinde durur. Rezervasyon tablosu varsa hücresini tutar."""
        robot.path = []
        if self.planner == "windowed":
            self.table.release(robot.id)
            self.table.reserve_path(robot.id, [robot.pos] * (self.window + 1), self._now, park_at_end=False)
        elif self.planner == "cooperative":
            self.table.release(robot.id)
            self.table.hold(robot.id, robot.pos, self._now)

    def _rebuild_grid(self) -> None:
        g = self.static_grid
        self.grid = Grid(g.width, g.height, g.blocked | self.temp_blocked)
        self.dist = DistanceMap(self.grid)

    def _plan_cooperative(self, robot: Robot) -> None:
        """Robotun eski rezervasyonlarını silip rezervasyon tablosuna göre yeniden planlar."""
        self.table.release(robot.id)
        stay = robot.phase in ("idle", "to_home")      # parka gidiyorsa hedefte süresiz kalacak
        cells = plan_cooperative(self.grid, self.table, robot.id, robot.pos, self._now,
                                 robot.target, stay_at_goal=stay)
        if cells:
            self.table.reserve_path(robot.id, cells, self._now, park_at_end=stay)
            robot.path = cells[1:]
        else:
            self.table.hold(robot.id, robot.pos, self._now)   # yol yoksa yerinde bekler, sonra tekrar dener
            robot.path = []

    def _plan_windowed(self, robot: Robot) -> None:
        """Robotun eski rezervasyonlarını silip önümüzdeki ``window`` adımı planlar (WHCA*)."""
        self.table.release(robot.id)
        cells = plan_windowed(self.grid, self.table, robot.id, robot.pos, self._now,
                              robot.target, self.window, self.dist)
        if cells is None:
            cells = [robot.pos, robot.pos]        # kıpırdayamıyorsa bir adım bekler, sonra tekrar dener
        self.table.reserve_path(robot.id, cells, self._now, park_at_end=False)
        robot.path = cells[1:]

    def _replan_all(self) -> None:
        """WHCA* için bütün robotları öncelik sırasıyla yeniden planlar."""
        self.table = ReservationTable()
        if self.priority is None:
            order = list(self.robots)
            self.rng.shuffle(order)
        else:
            order = self.priority.order(self)
        for r in order:
            self._plan_windowed(r)

    def _noisy_path(self, grid: Grid, start: Cell, goal: Cell, noise: float) -> list[Cell] | None:
        """A*, ama hedefe mesafe tahminine [0, noise) arası rastgele sayı ekleniyor (agitation).

        Takılıp duran robot böylece her seferinde biraz farklı yollar dener.
        """
        g = {start: 0}
        came_from: dict[Cell, Cell] = {}
        frontier = [(manhattan(start, goal), start)]
        while frontier:
            _, cell = heapq.heappop(frontier)
            if cell == goal:
                return reconstruct_path(came_from, goal)
            for n in grid.neighbors(cell):
                cost = g[cell] + 1
                if n not in g or cost < g[n]:
                    g[n] = cost
                    came_from[n] = cell
                    h = manhattan(n, goal) + self.rng.uniform(0, noise)
                    heapq.heappush(frontier, (cost + h, n))
        return None

    def step(self) -> None:
        self._now = self.t
        self._process_events()
        self._release_orders()
        self._assign_orders()
        if self.planner == "windowed" and self.t % self.replan_every == 0:
            self._replan_all()

        current = {r.id: r.pos for r in self.robots}
        planned = {r.id: (r.path[0] if r.path and not r.failed(self.t) else r.pos) for r in self.robots}
        intended = dict(planned)
        for rid, cell in intended.items():
            if cell in self.temp_blocked and cell != current[rid]:
                intended[rid] = current[rid]          # kapalı koridora giremez

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
            moved = intended[r.id] != r.pos
            on_task = r.phase in ("to_pick", "to_drop")
            if r.path and intended[r.id] == planned[r.id]:
                # plana uydu (planda bekleme adımı da olabilir)
                r.path.pop(0)
                r.blocked_for = 0
                if not moved and on_task:
                    r.task_waits += 1
            elif r.path:
                # çakışma yüzünden plandaki hücreye gidemedi
                r.blocked_for += 1
                if on_task:
                    r.task_waits += 1
            r.pos = intended[r.id]
            if moved:
                r.distance += 1

        self._now = self.t + 1
        for r in self.robots:
            if not r.failed(self._now):
                self._advance(r)

        occupied = {r.pos for r in self.robots}
        for r in self.robots:
            if r.failed(self._now):
                continue
            if self.cooperative:
                if r.blocked_for > 0:          # plandan saptı, rezervasyonları artık geçersiz
                    self.plan(r)
                    r.blocked_for = 0
                    self.repairs += 1
                continue
            if r.blocked_for >= self.repair_after:
                if self.use_agitation:
                    r.agitation += 1
                self.plan(r, avoid=occupied - {r.pos})
                r.blocked_for = 0
                self.repairs += 1

        self._track_stall()

        self.t += 1
        hook = getattr(self.station, "after_step", None)    # sadece RolloutLabeler'da var
        if hook is not None:
            hook(self)

    def _process_events(self) -> None:
        t = self.t
        for e in self.events:
            if e.kind == "block" and e.start == t:
                self.temp_blocked |= set(e.cells)
                self._rebuild_grid()
                if self.event_replan:
                    for r in self.robots:
                        if not r.failed(t) and set(r.path) & set(e.cells):
                            self.plan(r)
            elif e.kind == "block" and e.start + e.duration == t:
                self.temp_blocked -= set(e.cells)
                self._rebuild_grid()
                if self.event_replan:
                    self._replan_everyone()
            elif e.kind == "fail" and e.start == t:
                busy = [r for r in self.robots if r.phase in ("to_pick", "to_drop") and not r.failed(t)]
                chosen = self.event_rng.sample(busy, min(e.count, len(busy)))
                for r in chosen:
                    r.failed_until = t + e.duration
                    self._hold_failed(r)
                if self.allocation == "auction":
                    self._auction(reauction=True)       # arızalı robotun işi yeniden açık artırmaya çıkar
                if self.event_replan:
                    stuck = {r.pos for r in chosen}
                    for r in self.robots:
                        if not r.failed(t) and set(r.path) & stuck:
                            self.plan(r)
        for r in self.robots:
            if r.failed_until == t:                     # arıza bitti
                self.plan(r)

    def _replan_everyone(self) -> None:
        if self.planner == "windowed":
            self._replan_all()
        else:
            for r in self.robots:
                if r.phase != "idle" or r.pos != r.home:
                    self.plan(r)

    def _track_stall(self) -> None:
        if self.t < self.warmup:
            return
        busy = self.open_orders or any(r.phase in ("to_pick", "to_drop") for r in self.robots)
        since = self.t - max(self._last_completion, self.warmup)
        if self.in_stall and self._last_completion == self.t:
            self.in_stall = False
            self.stalls_resolved += 1
        elif not self.in_stall and busy and since >= self.stall_window:
            self.in_stall = True
            self.stalls += 1

    def _release_orders(self) -> None:
        while self._next_order < len(self.orders) and self.orders[self._next_order].arrival <= self.t:
            self.open_orders.append(self.orders[self._next_order])
            self._next_order += 1

    def _assign_orders(self) -> None:
        if self.allocation == "auction":
            self._auction(reauction=self.t % self.reauction_every == 0)
            return
        if not self.open_orders:
            return
        available = {r.id: r.pos for r in self.robots
                     if r.phase in ("idle", "to_home") and not r.failed(self.t)}
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

    def _auction(self, reauction: bool) -> None:
        """Bekleyen siparişleri açık artırmayla dağıtır.

        reauction ise robotların henüz rafa varmadığı siparişler de geri alınıp yeniden açık artırmaya çıkar.
        """
        now = self._now
        pool = list(self.open_orders)
        previous: dict[int, int] = {}       # sipariş id -> açık artırmadan önceki robotu
        released: set[int] = set()
        if reauction:
            for r in self.robots:
                if r.phase == "to_pick" and r.order is not None:
                    previous[r.order.id] = r.id
                    pool.append(r.order)
                    r.order = None
                    released.add(r.id)
                if r.next_order is not None:
                    previous[r.next_order.id] = r.id
                    pool.append(r.next_order)
                    r.next_order = None
        if not pool:
            return

        bidders: list[Bidder] = []
        for r in self.robots:
            if r.failed(now):
                continue
            if r.id in released or r.phase in ("idle", "to_home"):
                bidders.append(Bidder(r.id, 0, r.pos, 2))
            elif r.next_order is None and r.order is not None:
                if r.phase == "to_drop":
                    free_in = self.dist(r.pos, r.order.drop)
                else:
                    free_in = self.dist(r.pos, r.order.pick) + self.dist(r.order.pick, r.order.drop)
                bidders.append(Bidder(r.id, free_in, r.order.drop, 1))

        pool.sort(key=lambda o: (o.arrival, o.id))
        candidates = pool[:max(1, 2 * len(bidders))]
        by_id = {o.id: o for o in candidates}
        assigned: set[int] = set()
        for order_id, robot_id in auction(bidders, candidates, self.dist):
            r, o = self.robots[robot_id], by_id[order_id]
            assigned.add(order_id)
            if r.order is None:                     # boştaki robot hemen bu işe başlar
                r.order = o
                r.phase = "to_pick"
                if previous.get(order_id) != robot_id:
                    self.plan(r)
            else:                                   # meşgul robot bunu sıradaki işi olarak alır
                r.next_order = o
        for rid in released:
            r = self.robots[rid]
            if r.order is None:                     # işini kaybetti, yeni iş de almadı
                r.phase = "to_home"
                self.plan(r)
        self.open_orders = [o for o in pool if o.id not in assigned]

    def _advance(self, r: Robot) -> None:
        """Hedefine varan robotu görevinin sonraki aşamasına geçirir."""
        if r.pos != r.target:
            if not r.path and (r.phase != "idle" or self.planner == "windowed"):
                self.plan(r)           # yolu yok ya da pencere bitti
            return
        r.agitation = 0
        if r.phase == "to_pick":
            if self.station is not None:      # istasyon ürün alınınca seçilir
                i = self.station.choose(self, r)
                r.order = replace(r.order, drop=self.warehouse.drop_cells[i])
            r.phase = "to_drop"
            self.plan(r)
        elif r.phase == "to_drop":
            self.completion_times.append(self.t + 1 - r.order.arrival)
            self.completion_steps.append(self.t)
            if self.station is not None:
                self.station.on_delivery(r.id, self.t)
            self._last_completion = self.t
            self.task_waits_done += r.task_waits
            r.task_waits = 0
            if r.next_order is not None:        # açık artırmada kazanılmış sıradaki iş
                r.order, r.next_order = r.next_order, None
                r.phase = "to_pick"
            else:
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
            stalls=self.stalls,
            stalls_resolved=self.stalls_resolved,
            deadlocked=int(self.in_stall),
        )
