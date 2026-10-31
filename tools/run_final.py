"""Final deneyi. Bütün politikalar bütün depo düzenlerinde çalıştırılır.

    uv run python tools/run_final.py            # hepsi
    uv run python tools/run_final.py movingai   # sadece bir düzen

Karşılaştırılan politikalar şunlar.
  P0       bağımsız A* + Local Repair (Silver 2005)
  P1       WHCA*, pencere 16, 8 adımda bir yeniden planlama (Silver 2005)
  P2       P1 + sıralı açık artırma (Koenig 2006) + olay olunca yeniden planlama
  P3-rule  P2 + kural tabanlı istasyon seçimi ve öncelik sırası
  P3       P2 + öğrenilmiş istasyon seçimi ve öncelik ağırlıkları
Depo düzenleri low, medium, high (warehouse.py) ve MovingAI'daki warehouse-10-20-10-2-1 (161x63).
Modeller sadece medium düzende eğitildi. Diğer düzenlerde aynı modeller kullanılıyor.
Kendi ürettiğimiz düzenlerde 0-29, movingai'de 0-9 seed'leri kullanılır.
Sonuçlar results/final.csv dosyasına yazılır (tek düzen verilirse results/final_<düzen>.csv).
"""

from __future__ import annotations

import csv
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from functools import cache
from pathlib import Path

import numpy as np

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.priority import LinearPriority, heuristic
from warehouse_mapf.sim import Simulation
from warehouse_mapf.stations import LearnedStation, QueueAwareStation
from warehouse_mapf.warehouse import generate_warehouse, load_movingai

ROOT = Path(__file__).resolve().parent.parent
WARMUP, HORIZON = 200, 1000

# düzen -> (robot sayıları, geliş hızları, seed'ler)
LAYOUTS = {
    "low":      ([10, 20, 30], [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2], range(30)),
    "medium":   ([10, 20, 30], [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2], range(30)),
    "high":     ([10, 20, 30], [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2], range(30)),
    "movingai": ([50, 100], [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5], range(10)),
}
POLICIES = ["P0", "P1", "P2", "P3-rule", "P3"]


@cache
def warehouse(layout: str):
    if layout == "movingai":
        return load_movingai(ROOT / "maps" / "warehouse-10-20-10-2-1.map")
    return generate_warehouse(density=layout)


def options(policy: str) -> dict:
    if policy == "P0":
        return {}
    if policy == "P1":
        return {"planner": "windowed"}
    p2 = {"planner": "windowed", "allocation": "auction", "event_replan": True}
    if policy == "P2":
        return p2
    if policy == "P3-rule":
        alpha = json.loads((ROOT / "models" / "station_rule.json").read_text())["alpha"]
        return {**p2, "station": QueueAwareStation(alpha), "priority": heuristic("carrying-first")}
    data = json.loads((ROOT / "models" / "priority_policy.json").read_text())
    priority = LinearPriority(np.array(data["weights"]) / np.array(data["scale"]), name="learned")
    return {**p2, "station": LearnedStation.load(ROOT / "models" / "station_policy.json"), "priority": priority}


def run_one(job) -> dict:
    layout, policy, robots, rate, seed = job
    w = warehouse(layout)
    orders = generate_orders(w, rate, WARMUP + HORIZON, random.Random(seed))
    m = Simulation(w, orders, robots, greedy_assign, horizon=HORIZON, warmup=WARMUP, seed=seed,
                   **options(policy)).run()
    return {"layout": layout, "policy": policy, "rate": rate, "seed": seed, **asdict(m)}


def main() -> None:
    layouts = sys.argv[1:] or list(LAYOUTS)
    jobs = [(lay, p, n, r, s)
            for lay in layouts
            for p in POLICIES
            for n in LAYOUTS[lay][0] for r in LAYOUTS[lay][1] for s in LAYOUTS[lay][2]]
    jobs.sort(key=lambda j: j[0] != "movingai")     # uzun süren movingai işleri önce başlasın
    rows = []
    with ProcessPoolExecutor() as pool:
        for i, row in enumerate(pool.map(run_one, jobs, chunksize=2), 1):
            rows.append(row)
            if i % 200 == 0 or i == len(jobs):
                print(f"{i}/{len(jobs)}", flush=True)
    out = ROOT / "results" / ("final.csv" if len(layouts) == len(LAYOUTS) else f"final_{'_'.join(layouts)}.csv")
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} simülasyon -> {out}")


if __name__ == "__main__":
    main()
