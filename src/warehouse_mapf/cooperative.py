"""Cooperative A* (CA*) ve pencereli sürümü WHCA*.

Robotlar sırayla planlanır. Planlanan yol rezervasyon tablosuna yazılır. Sonraki robotlar
tablodaki (hücre, zaman) çiftlerine giremez. Aramada her düğüm bir (hücre, zaman) çifti,
yerinde beklemek de bir hamle.

plan_cooperative hedefe kadar bütün yolu ayırır. plan_windowed sadece önümüzdeki window
adımı ayırır, gerisi için engellere göre gerçek mesafeyi (DistanceMap) kullanır.
"""

from __future__ import annotations

import heapq
from collections import defaultdict, deque

from .astar import manhattan
from .grid import Cell, Grid


class ReservationTable:
    """Hangi hücrenin hangi zamanda hangi robota ayrıldığını tutar.

    vertex: (hücre, t) -> robot
    edge: (a, b, t) -> robot, t ile t+1 arasında a'dan b'ye geçiş (iki robot yer değiştirmesin diye)
    park: hücre -> (robot, t), robot t anından sonra orada süresiz duruyor
    """

    def __init__(self) -> None:
        self.vertex: dict[tuple[Cell, int], int] = {}
        self.edge: dict[tuple[Cell, Cell, int], int] = {}
        self.park: dict[Cell, tuple[int, int]] = {}
        self.cell_times: dict[Cell, set[int]] = defaultdict(set)   # hücre -> rezerve edildiği zamanlar
        self._owned: dict[int, list] = defaultdict(list)          # robot -> kendi kayıtları

    def reserve_path(self, robot: int, cells: list[Cell], t0: int, park_at_end: bool) -> None:
        """``cells[k]``, robotun ``t0 + k`` anındaki hücresi."""
        for k, c in enumerate(cells):
            self._vertex(robot, c, t0 + k)
            if k > 0:
                self._edge(robot, cells[k - 1], c, t0 + k - 1)
        if park_at_end:
            self.hold(robot, cells[-1], t0 + len(cells) - 1)

    def hold(self, robot: int, cell: Cell, t: int) -> None:
        """Robot ``t`` anından itibaren ``cell``'de süresiz bekleyecek."""
        self.park[cell] = (robot, t)
        self._owned[robot].append(("park", cell))

    def release(self, robot: int) -> None:
        """Robotun bütün rezervasyonlarını siler (yeniden planlamadan önce)."""
        for kind, key in self._owned.pop(robot, []):
            if kind == "vertex":
                if self.vertex.get(key) == robot:
                    del self.vertex[key]
                    self.cell_times[key[0]].discard(key[1])
            elif kind == "edge":
                if self.edge.get(key) == robot:
                    del self.edge[key]
            elif self.park.get(key, (None,))[0] == robot:
                del self.park[key]

    def _vertex(self, robot: int, cell: Cell, t: int) -> None:
        self.vertex[(cell, t)] = robot
        self.cell_times[cell].add(t)
        self._owned[robot].append(("vertex", (cell, t)))

    def _edge(self, robot: int, a: Cell, b: Cell, t: int) -> None:
        self.edge[(a, b, t)] = robot
        self._owned[robot].append(("edge", (a, b, t)))

    def free(self, robot: int, cell: Cell, t: int) -> bool:
        """Robot ``t`` anında ``cell``'de olabilir mi?"""
        owner = self.vertex.get((cell, t))
        if owner is not None and owner != robot:
            return False
        parked = self.park.get(cell)
        return not (parked and parked[0] != robot and parked[1] <= t)

    def can_move(self, robot: int, a: Cell, b: Cell, t: int) -> bool:
        """t ile t+1 arasında a'dan b'ye geçiş başka bir robotla yer değiştirmeye yol açıyor mu?"""
        owner = self.edge.get((b, a, t))
        return owner is None or owner == robot

    def free_forever(self, robot: int, cell: Cell, t: int) -> bool:
        """Robot ``t`` anından sonra bu hücrede süresiz durabilir mi?"""
        if not self.free(robot, cell, t):
            return False
        return all(tt < t or self.vertex.get((cell, tt)) == robot for tt in self.cell_times.get(cell, ()))


def plan_cooperative(grid: Grid, table: ReservationTable, robot: int, start: Cell, t0: int,
                     goal: Cell, stay_at_goal: bool, max_steps: int | None = None,
                     max_expansions: int = 20000) -> list[Cell] | None:
    """Zamanı da hesaba katan A*. Rezervasyonlara çarpmayan yolu döndürür, bulamazsa None.

    Listede her adım için bir hücre var, ilk eleman t0 anındaki start. Beklemek aynı hücrenin
    tekrar yazılması demek. stay_at_goal ise robot hedefte kalacağı için hedef hücre sonrasında
    da boş olmalı.
    """
    if max_steps is None:
        max_steps = 3 * manhattan(start, goal) + 60

    def at_goal(cell: Cell, t: int) -> bool:
        if cell != goal:
            return False
        return table.free_forever(robot, cell, t) if stay_at_goal else True

    start_node = (start, t0)
    g = {start_node: 0}
    came_from: dict[tuple[Cell, int], tuple[Cell, int]] = {}
    frontier = [(manhattan(start, goal), 0, start, t0)]
    expansions = 0
    while frontier:
        _, steps, cell, t = heapq.heappop(frontier)
        expansions += 1
        if expansions > max_expansions:
            return None
        if at_goal(cell, t):
            node = (cell, t)
            path = [cell]
            while node in came_from:
                node = came_from[node]
                path.append(node[0])
            return path[::-1]
        if steps >= max_steps:
            continue
        for n in grid.neighbors(cell) + [cell]:          # dört yön + yerinde bekle
            nt = t + 1
            if not table.free(robot, n, nt):
                continue
            if n != cell and not table.can_move(robot, cell, n, t):
                continue
            node = (n, nt)
            if node not in g or steps + 1 < g[node]:
                g[node] = steps + 1
                came_from[node] = (cell, t)
                heapq.heappush(frontier, (steps + 1 + manhattan(n, goal), steps + 1, n, nt))
    return None


class DistanceMap:
    """Engellere göre gerçek mesafe, robotlar yok sayılır.

    Her hedef için bir kez BFS yapılır ve sonuç saklanır.
    """

    def __init__(self, grid: Grid):
        self.grid = grid
        self._cache: dict[Cell, dict[Cell, int]] = {}

    def __call__(self, cell: Cell, goal: Cell) -> int:
        table = self._cache.get(goal)
        if table is None:
            table = {goal: 0}
            queue = deque([goal])
            while queue:
                c = queue.popleft()
                for n in self.grid.neighbors(c):
                    if n not in table:
                        table[n] = table[c] + 1
                        queue.append(n)
            self._cache[goal] = table
        return table.get(cell, 10**6)


def plan_windowed(grid: Grid, table: ReservationTable, robot: int, start: Cell, t0: int,
                  goal: Cell, window: int, dist: DistanceMap) -> list[Cell] | None:
    """WHCA* için sadece önümüzdeki window adımı planlar.

    Her adımın maliyeti 1, hedefte beklemenin maliyeti 0. Pencere sonunda hedefe kalan
    mesafe tahmin olarak eklenir. window + 1 hücre döner, pencerede yol yoksa None.
    """
    frontier = [(dist(start, goal), 0, 0, start)]       # (f, g, adım, hücre)
    g = {(start, 0): 0}
    came_from: dict[tuple[Cell, int], tuple[Cell, int]] = {}
    while frontier:
        _, cost, k, cell = heapq.heappop(frontier)
        if cost > g.get((cell, k), cost):
            continue
        if k == window:
            node, path = (cell, k), [cell]
            while node in came_from:
                node = came_from[node]
                path.append(node[0])
            return path[::-1]
        t = t0 + k
        for n in grid.neighbors(cell) + [cell]:
            if not table.free(robot, n, t + 1):
                continue
            if n != cell and not table.can_move(robot, cell, n, t):
                continue
            step_cost = 0 if (n == cell == goal) else 1
            node = (n, k + 1)
            new = cost + step_cost
            if new < g.get(node, 10**9):
                g[node] = new
                came_from[node] = (cell, k)
                heapq.heappush(frontier, (new + dist(n, goal), new, k + 1, n))
    return None
