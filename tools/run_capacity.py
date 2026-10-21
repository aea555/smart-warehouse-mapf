"""Kapasite eğrisi deneyi. Sipariş hızı arttıkça her politikanın throughput'unun nasıl değiştiğine bakar.

    uv run python tools/run_capacity.py

Her (politika, robot sayısı, geliş hızı, seed) birleşimi için bir simülasyon çalıştırılır.
Sonuçlar results/capacity.csv dosyasına yazılır, grafiği tools/plot_capacity.py çizer.
"""

from __future__ import annotations

import csv
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.sim import Simulation
from warehouse_mapf.warehouse import generate_warehouse

WARMUP = 200
HORIZON = 1000
SEEDS = range(10)
DENSITY = "medium"
ROBOTS = [10, 20, 30]
RATES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.2]   # adım başına beklenen sipariş
POLICIES = {
    "P0": {"agitation": True},                 # baseline, bağımsız A* + Local Repair
    "P1-CA": {"planner": "cooperative"},       # Cooperative A*, rotanın tamamı rezerve edilir
    "P1": {"planner": "windowed"},             # WHCA*, sadece 16 adımlık pencere rezerve edilir
}

OUT = Path(__file__).resolve().parent.parent / "results" / "capacity.csv"


def run_one(job: tuple[str, int, float, int]) -> dict:
    policy, robots, rate, seed = job
    warehouse = generate_warehouse(density=DENSITY)
    orders = generate_orders(warehouse, rate, WARMUP + HORIZON, random.Random(seed))
    metrics = Simulation(warehouse, orders, robots, greedy_assign, horizon=HORIZON,
                         warmup=WARMUP, seed=seed, **POLICIES[policy]).run()
    return {"policy": policy, "density": DENSITY, "rate": rate, "seed": seed, **asdict(metrics)}


def main() -> None:
    jobs = [(p, n, r, s) for p in POLICIES for n in ROBOTS for r in RATES for s in SEEDS]
    rows = []
    with ProcessPoolExecutor() as pool:
        for i, row in enumerate(pool.map(run_one, jobs, chunksize=2), 1):
            rows.append(row)
            if i % 50 == 0 or i == len(jobs):
                print(f"{i}/{len(jobs)}", flush=True)
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} satır -> {OUT}")


if __name__ == "__main__":
    main()
