"""İstasyon seçicilerinin test değerlendirmesi (RQ3).

    uv run python tools/run_station.py

Test seed'leri 0-29. Bunlar eğitimde ve doğrulamada hiç kullanılmadı.
Geri kalan her şey aynı, hepsinde WHCA* + açık artırma kullanılıyor.
Karşılaştırılan istasyon seçiciler şunlar.
  random       siparişle birlikte gelen rastgele istasyon
  nearest      en yakın istasyon
  rule         kural tabanlı, alpha doğrulamada seçildi (models/station_rule.json)
  learned      robotun kendi teslim süresinden öğrenir (models/station_policy.json)
Sonuçlar results/station_test.csv dosyasına yazılır.
"""

from __future__ import annotations

import csv
import json
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.sim import Simulation
from warehouse_mapf.stations import LearnedStation, NearestStation, QueueAwareStation
from warehouse_mapf.warehouse import generate_warehouse

ROOT = Path(__file__).resolve().parent.parent
WARMUP, HORIZON = 200, 1000
DENSITY = "medium"
ROBOTS = [20, 30]
RATES = [0.45, 0.6, 0.8]
TEST_SEEDS = range(30)
SELECTORS = ["random", "nearest", "rule", "learned"]


def make(selector: str):
    if selector == "random":
        return None
    if selector == "nearest":
        return NearestStation()
    if selector == "rule":
        return QueueAwareStation(json.loads((ROOT / "models" / "station_rule.json").read_text())["alpha"])
    return LearnedStation.load(ROOT / "models" / "station_policy.json")


def run_one(job):
    selector, robots, rate, seed = job
    warehouse = generate_warehouse(density=DENSITY)
    orders = generate_orders(warehouse, rate, WARMUP + HORIZON, random.Random(seed))
    m = Simulation(warehouse, orders, robots, greedy_assign, horizon=HORIZON, warmup=WARMUP, seed=seed,
                   planner="windowed", allocation="auction", station=make(selector)).run()
    return {"selector": selector, "rate": rate, "seed": seed, **asdict(m)}


def main() -> None:
    jobs = [(s, n, r, seed) for s in SELECTORS for n in ROBOTS for r in RATES for seed in TEST_SEEDS]
    with ProcessPoolExecutor() as pool:
        rows = list(pool.map(run_one, jobs, chunksize=4))
    out = ROOT / "results" / "station_test.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} simülasyon -> {out}")


if __name__ == "__main__":
    main()
