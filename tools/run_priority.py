"""WHCA*'ta robotların planlanma sırasını belirleyen yöntemleri test seed'lerinde karşılaştırır.

    uv run python tools/run_priority.py

Test seed'leri 0-29. Geri kalan her şey aynı, hepsinde WHCA* + açık artırma + öğrenilmiş istasyon
seçici (v1) kullanılıyor. Karşılaştırılan sıralar şunlar.
  random          rastgele sıra (WHCA*'ın normal hali)
  carrying-first  kural tabanlı, önce ürün taşıyanlar, sonra hedefi uzak olanlar
  learned         CEM ile öğrenilen doğrusal puan (models/priority_policy.json)
Sonuçlar results/priority_test.csv dosyasına yazılır.
"""

from __future__ import annotations

import csv
import json
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.priority import LinearPriority, heuristic
from warehouse_mapf.sim import Simulation
from warehouse_mapf.stations import LearnedStation
from warehouse_mapf.warehouse import generate_warehouse

ROOT = Path(__file__).resolve().parent.parent
WARMUP, HORIZON = 200, 1000
DENSITY = "medium"
ROBOTS = [20, 30]
RATES = [0.45, 0.6, 0.8]
TEST_SEEDS = range(30)
POLICIES = ["random", "carrying-first", "learned"]


def make(name: str):
    if name == "random":
        return None
    if name == "learned":
        data = json.loads((ROOT / "models" / "priority_policy.json").read_text())
        return LinearPriority(np.array(data["weights"]) / np.array(data["scale"]), name="learned")
    return heuristic(name)


def run_one(job):
    name, robots, rate, seed = job
    warehouse = generate_warehouse(density=DENSITY)
    orders = generate_orders(warehouse, rate, WARMUP + HORIZON, random.Random(seed))
    m = Simulation(warehouse, orders, robots, greedy_assign, horizon=HORIZON, warmup=WARMUP, seed=seed,
                   planner="windowed", allocation="auction", priority=make(name),
                   station=LearnedStation.load(ROOT / "models" / "station_policy.json")).run()
    return {"priority": name, "rate": rate, "seed": seed, **asdict(m)}


def main() -> None:
    jobs = [(p, n, r, s) for p in POLICIES for n in ROBOTS for r in RATES for s in TEST_SEEDS]
    with ProcessPoolExecutor() as pool:
        rows = list(pool.map(run_one, jobs, chunksize=4))
    out = ROOT / "results" / "priority_test.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} simülasyon -> {out}")


if __name__ == "__main__":
    main()
