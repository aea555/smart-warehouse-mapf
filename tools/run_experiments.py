"""Deney ızgarasını çalıştırır ve sonuçları CSV'ye yazar.

    uv run python tools/run_experiments.py

Her (yük, raf yoğunluğu, seed) birleşimi için bir simülasyon çalıştırılır.
Aynı seed her politikada aynı siparişleri üretir, böylece karşılaştırma adil olur.
"""

from __future__ import annotations

import csv
import random
from dataclasses import asdict
from pathlib import Path

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.sim import Simulation
from warehouse_mapf.warehouse import generate_warehouse

HORIZON = 1000   # ölçülen adım sayısı
SEEDS = range(10)
DENSITIES = ["low", "medium", "high"]
# yük seviyesi -> (robot sayısı, adım başına sipariş)
LOADS = {"low": (10, 0.15), "medium": (20, 0.30), "high": (30, 0.45)}
POLICIES = {"P0_greedy_independent": greedy_assign}

OUT = Path(__file__).resolve().parent.parent / "results" / "experiments.csv"


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    rows = []
    for policy, assign in POLICIES.items():
        for density in DENSITIES:
            warehouse = generate_warehouse(density=density)
            for load, (robots, rate) in LOADS.items():
                for seed in SEEDS:
                    orders = generate_orders(warehouse, rate, HORIZON, random.Random(seed))
                    metrics = Simulation(warehouse, orders, robots, assign, horizon=HORIZON).run()
                    rows.append({"policy": policy, "density": density, "load": load,
                                 "rate": rate, "seed": seed, **asdict(metrics)})
                print(f"{policy} {density} {load} tamam")
    with OUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} satır -> {OUT}")


if __name__ == "__main__":
    main()
