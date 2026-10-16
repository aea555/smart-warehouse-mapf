"""Simülasyonları adım adım kaydeder ve Unity'de oynatılacak JSON dosyasını yazar.

    uv run python tools/export_replay.py

Birkaç farklı yükte P0 ayrı ayrı çalıştırılır ve hepsi tek dosyaya yazılır.
Unity hiçbir şey hesaplamaz, sadece bu kaydı oynatır.
Kayıt unity/Assets/StreamingAssets/replay.json dosyasına yazılır.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.sim import Simulation
from warehouse_mapf.warehouse import generate_warehouse

HORIZON = 1000
PHASES = {"idle": 0, "to_pick": 1, "to_drop": 2, "to_home": 3}
# (etiket, raf yoğunluğu, robot, adım başına sipariş, seed)
RUNS = [
    ("Düşük yük", "medium", 10, 0.15, 0),
    ("Orta yük", "medium", 20, 0.30, 0),
    ("Yüksek yük (akıyor)", "medium", 30, 0.45, 6),
    ("Yüksek yük (kilitleniyor)", "medium", 30, 0.45, 9),
]

OUT = Path(__file__).resolve().parent.parent / "unity" / "Assets" / "StreamingAssets" / "replay.json"


def xy(cells):
    return [{"x": x, "y": y} for x, y in sorted(cells)]


def record(label, density, robots, rate, seed):
    warehouse = generate_warehouse(density=density)
    grid = warehouse.grid
    orders = generate_orders(warehouse, rate, HORIZON, random.Random(seed))
    sim = Simulation(warehouse, orders, robots, greedy_assign, horizon=HORIZON)

    # Planlar bir kez yazılır, her adımda robot için sadece (plan no, plandaki yeri) tutulur.
    # Dosya böyle küçük kalıyor, kalan rota Unity tarafında bundan bulunur.
    plans: list[dict] = []
    active: list[tuple[int, list]] = [(-1, [])] * robots

    def plan_ref(r):
        path = list(r.path)
        if not path:
            return -1, 0
        pid, cells = active[r.id]
        start = len(cells) - len(path)
        if pid < 0 or start < 0 or cells[start:] != path:
            plans.append({"xs": [c[0] for c in path], "ys": [c[1] for c in path]})
            pid, cells, start = len(plans) - 1, path, 0
            active[r.id] = (pid, cells)
        return pid, start

    def frame():
        refs = [plan_ref(r) for r in sim.robots]
        return {
            "plan": [p for p, _ in refs],
            "planOffset": [o for _, o in refs],
            "order": [r.order.id if r.order else -1 for r in sim.robots],
            "tx": [r.target[0] for r in sim.robots],
            "ty": [r.target[1] for r in sim.robots],
            "xs": [r.pos[0] for r in sim.robots],
            "ys": [r.pos[1] for r in sim.robots],
            # robotun bir sonraki adımda gitmek istediği hücre, yolu yoksa kendi hücresi
            "nx": [(r.path[0] if r.path else r.pos)[0] for r in sim.robots],
            "ny": [(r.path[0] if r.path else r.pos)[1] for r in sim.robots],
            "phase": [PHASES[r.phase] for r in sim.robots],
            "blocked": [r.blocked_for for r in sim.robots],
            "openPicks": xy({o.pick for o in sim.open_orders}),
            "arrived": sim._next_order,
            "open": len(sim.open_orders),
            "completed": len(sim.completion_times),
            "conflicts": sim.conflicts,
        }

    frames = [frame()]
    while sim.t < HORIZON:
        sim.step()
        frames.append(frame())

    stations = {c for c in grid.blocked if c[0] == grid.width - 1}
    return {
        "label": label,
        "policy": "P0: greedy atama + bağımsız A* (Local Repair)",
        "density": density,
        "robots": robots,
        "rate": rate,
        "seed": seed,
        "width": grid.width,
        "height": grid.height,
        "shelves": xy(grid.blocked - stations),
        "stations": xy(stations),
        "drops": xy(warehouse.drop_cells),
        "parks": xy(warehouse.park_cells),
        "ordersArrived": sim._next_order,
        "orders": [{"id": o.id, "arrival": o.arrival, "pick": {"x": o.pick[0], "y": o.pick[1]},
                    "drop": {"x": o.drop[0], "y": o.drop[1]}} for o in orders],
        "plans": plans,
        "frames": frames,
    }


def main() -> None:
    runs = [record(*r) for r in RUNS]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"runs": runs}, ensure_ascii=False, separators=(",", ":")))
    for r in runs:
        last = r["frames"][-1]
        print(f'{r["label"]} seed {r["seed"]}: {last["completed"]}/{r["ordersArrived"]} sipariş, {last["conflicts"]} çakışma')
    print(f"{OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
