"""Simülasyonları adım adım kaydeder ve Unity'de oynatılacak JSON dosyalarını yazar.

    uv run python tools/export_replay.py

Her senaryo P0, P1, P2 ve P3 ile ayrı ayrı çalıştırılır. Aynı senaryoda siparişler aynıdır.
Unity hiçbir şey hesaplamaz, sadece bu kayıtları oynatır.
Kayıtlar unity/Assets/StreamingAssets/replays/ altına yazılır. index.json senaryo listesini ve her adımın
özet metriklerini tutar. <senaryo>_<politika>.json dosyaları ise simülasyonların tam kaydıdır
(konumlar, planlar, siparişler).
"""

from __future__ import annotations

import json
import random
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.policies import policy_options
from warehouse_mapf.sim import Event, Simulation
from warehouse_mapf.warehouse import generate_warehouse, load_movingai

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "unity" / "Assets" / "StreamingAssets" / "replays"
WARMUP, HORIZON = 200, 1000
PHASES = {"idle": 0, "to_pick": 1, "to_drop": 2, "to_home": 3}

# id -> (kısa ad, açıklama)
POLICIES = {
    "P0": ("Bağımsız A*", "Her robot kendi yolunu planlar, çarpışma olunca yerel olarak onarır (Local Repair A*)."),
    "P1": ("WHCA*", "Robotlar sırayla, rezervasyon tablosuna bakarak 16 adımlık pencerede birlikte planlanır."),
    "P2": ("+ açık artırma", "WHCA* + siparişler en ucuz teklifi veren robota dağıtılır, olayda yeniden planlanır."),
    "P3": ("+ öğrenen modeller", "P2 + paketleme masasını ve planlama sırasını öğrenilmiş modeller seçer."),
}
BLOCK = tuple((x, 10) for x in range(14, 26))
# id -> (başlık, açıklama, düzen, robot, adım başına sipariş, seed, olaylar)
SCENARIOS = {
    "normal": ("Normal gün", "30 robot, orta yük. Bütün politikalar talebe yetişebilmeli.",
               "medium", 30, 0.45, 3, ()),
    "busy": ("Yoğun gün", "30 robot, kapasitenin üstünde sipariş. Fark burada açılır.",
             "medium", 30, 0.8, 3, ()),
    "block": ("Koridor kapandı", "500. adımda orta koridorun 12 hücresi 300 adımlığına kapanır.",
              "medium", 30, 0.6, 3, (Event("block", 500, 300, cells=BLOCK),)),
    "fail": ("Robot arızası", "500. adımda 5 robot 300 adımlığına yerinde arızalanır.",
             "medium", 30, 0.6, 3, (Event("fail", 500, 300, count=5),)),
    "big": ("Büyük depo (MovingAI)", "Benchmark haritası warehouse-10-20-10-2-1, 100 robot. Modeller burada eğitilmedi.",
            "movingai", 100, 0.8, 0, ()),
}


def warehouse(layout: str):
    if layout == "movingai":
        return load_movingai(ROOT / "maps" / "warehouse-10-20-10-2-1.map")
    return generate_warehouse(density=layout)


def xy(cells):
    return [{"x": x, "y": y} for x, y in sorted(cells)]


def record(job):
    sid, policy = job
    title, about, layout, robots, rate, seed, events = SCENARIOS[sid]
    w = warehouse(layout)
    grid = w.grid
    orders = generate_orders(w, rate, WARMUP + HORIZON, random.Random(seed))
    sim = Simulation(w, orders, robots, greedy_assign, horizon=HORIZON, warmup=WARMUP, seed=seed,
                     events=events, **policy_options(policy))

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
            "failed": [r.id for r in sim.robots if r.failed(sim.t)],
            "closed": xy(sim.temp_blocked),
            "openPicks": xy({o.pick for o in sim.open_orders}),
            "arrived": sim._next_order,
            "open": len(sim.open_orders),
            "completed": len(sim.completion_times),
            "conflicts": sim.conflicts,
        }

    # ısınma bittikten sonraki adımların özeti
    summary = {"completed": [], "meanTime": [], "open": [], "stuck": []}

    def summarize():
        times = [ct for s, ct in zip(sim.completion_steps, sim.completion_times) if s >= WARMUP]
        summary["completed"].append(len(times))
        summary["meanTime"].append(round(sum(times) / len(times), 1) if times else 0)
        summary["open"].append(len(sim.open_orders))
        summary["stuck"].append(sum(1 for r in sim.robots if r.blocked_for > 0))

    frames = [frame()]
    summarize()
    while sim.t < WARMUP + HORIZON:
        sim.step()
        frames.append(frame())
        summarize()

    static = set(grid.blocked)
    drops = set(w.drop_cells)
    stations = {(x, y) for (x, y) in static if x in (0, grid.width - 1)
                and ((x - 1, y) in drops or (x + 1, y) in drops)}
    walls = {(x, y) for (x, y) in static - stations
             if x in (0, grid.width - 1) or y in (0, grid.height - 1)}
    run = {
        "scenario": sid,
        "label": title,
        "policyId": policy,
        "policy": POLICIES[policy][0],
        "density": layout,
        "robots": robots,
        "rate": rate,
        "seed": seed,
        "warmup": WARMUP,
        "width": grid.width,
        "height": grid.height,
        "shelves": xy(static - stations - walls),
        "walls": xy(walls),
        "stations": xy(stations),
        "drops": xy(w.drop_cells),
        "parks": xy(w.park_cells),
        "ordersArrived": sim._next_order,
        "orders": [{"id": o.id, "arrival": o.arrival, "pick": {"x": o.pick[0], "y": o.pick[1]},
                    "drop": {"x": o.drop[0], "y": o.drop[1]}} for o in orders],
        "plans": plans,
        "frames": frames,
    }
    (OUT / f"{sid}_{policy}.json").write_text(json.dumps(run, ensure_ascii=False, separators=(",", ":")))
    return sid, policy, summary


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    jobs = [(s, p) for s in SCENARIOS for p in POLICIES]
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(record, jobs))
    summaries = {(s, p): summ for s, p, summ in results}

    index = {"policies": [{"id": p, "name": n, "about": a} for p, (n, a) in POLICIES.items()], "scenarios": []}
    for sid, (title, about, layout, robots, rate, seed, events) in SCENARIOS.items():
        index["scenarios"].append({
            "id": sid, "title": title, "about": about, "robots": robots, "rate": rate, "seed": seed,
            "warmup": WARMUP,
            "events": [{"kind": e.kind, "start": e.start, "duration": e.duration} for e in events],
            "series": [{"policy": p, **summaries[(sid, p)]} for p in POLICIES],
        })
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    for sid in SCENARIOS:
        line = "  ".join(f"{p}: {summaries[(sid, p)]['completed'][-1]} sipariş, "
                         f"{summaries[(sid, p)]['meanTime'][-1]:.0f} adım" for p in POLICIES)
        print(f"{sid:<7} {line}")
    size = sum(f.stat().st_size for f in OUT.iterdir()) // (1024 * 1024)
    print(f"{OUT} ({size} MB)")


if __name__ == "__main__":
    main()
