"""WHCA* pencere boyu duyarlılık analizi.

    uv run python tools/run_sensitivity.py

Pencere boyu (window) değiştirilir. Yeniden planlama aralığı her seferinde pencerenin yarısı (Silver 2005).
Sonuçlar results/sensitivity.csv dosyasına yazılır.
"""

from __future__ import annotations

import csv
import random
import time
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
ROBOTS = 30
RATES = [0.45, 0.8]          # yüksek yük ve kapasitenin üstünde bir yük
WINDOWS = [4, 8, 16, 32]

OUT = Path(__file__).resolve().parent.parent / "results" / "sensitivity.csv"


def run_one(job: tuple[int, float, int]) -> dict:
    window, rate, seed = job
    warehouse = generate_warehouse(density=DENSITY)
    orders = generate_orders(warehouse, rate, WARMUP + HORIZON, random.Random(seed))
    start = time.perf_counter()
    metrics = Simulation(warehouse, orders, ROBOTS, greedy_assign, horizon=HORIZON, warmup=WARMUP,
                         seed=seed, planner="windowed", window=window,
                         replan_every=max(1, window // 2)).run()
    seconds = time.perf_counter() - start
    return {"window": window, "replan_every": max(1, window // 2), "rate": rate, "seed": seed,
            "seconds": round(seconds, 3), **asdict(metrics)}


def main() -> None:
    jobs = [(w, r, s) for w in WINDOWS for r in RATES for s in SEEDS]
    with ProcessPoolExecutor() as pool:
        rows = list(pool.map(run_one, jobs))
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} satır -> {OUT}")


if __name__ == "__main__":
    main()
