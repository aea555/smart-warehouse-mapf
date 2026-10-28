"""İstasyon seçicinin v2 denemesini eğitir. Final deneylerde kullanılmadı.

    uv run python tools/train_station_v2.py

v1'den üç farkı var.
1. Her karar anında simülasyon kopyalanır ve robot sırayla her istasyona gönderilir.
2. Kopyada sonraki 60 adımda bütün depoda yapılan teslimat sayılır, bu istasyonun etiketi olur
   (RolloutLabeler).
3. Model mutlak değeri değil, o karardaki 4 istasyonun ortalamasından farkı öğrenir.
Durumda yoldaki robot sayısı ve genel yük de var. Testte kopya yok, tahmini en yüksek istasyon seçilir.
Eğitimde 1000-1039, doğrulamada 2000-2009 seed'leri kullanılır.
Model models/station_policy_v2.json dosyasına yazılır.
"""

from __future__ import annotations

import json
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.sim import Simulation
from warehouse_mapf.stations import LearnedStation, RolloutLabeler
from warehouse_mapf.warehouse import generate_warehouse

ROOT = Path(__file__).resolve().parent.parent
WARMUP, HORIZON = 200, 1000
ROBOTS, DENSITY = 30, "medium"
RATES = [0.45, 0.6, 0.8]
TRAIN_SEEDS = range(1000, 1040)
VAL_SEEDS = range(2000, 2010)
RIDGES = [0.1, 1.0, 10.0, 100.0, 1000.0]


def simulate(seed: int, rate: float, station):
    warehouse = generate_warehouse(density=DENSITY)
    orders = generate_orders(warehouse, rate, WARMUP + HORIZON, random.Random(seed))
    return Simulation(warehouse, orders, ROBOTS, greedy_assign, horizon=HORIZON, warmup=WARMUP,
                      seed=seed, planner="windowed", allocation="auction", station=station).run()


def collect(job):
    k, seed = job
    labeler = RolloutLabeler(alpha=2.0, epsilon=0.1, sample=0.25, horizon=60, seed=seed)
    simulate(seed, RATES[k % len(RATES)], labeler)
    return np.array(labeler.X), np.array(labeler.y)


def validate(agent: LearnedStation, rate: float, seed: int):
    m = simulate(seed, rate, agent)
    return m.throughput, m.mean_completion_time


DATA = ROOT / "results" / "station_rollouts.npz"


def main() -> None:
    if DATA.exists():
        data = np.load(DATA)
        X, y = data["X"], data["y"]
    else:
        with ProcessPoolExecutor() as pool:
            parts = list(pool.map(collect, enumerate(TRAIN_SEEDS)))
        X = np.concatenate([p[0] for p in parts])
        y = np.concatenate([p[1] for p in parts])
        np.savez(DATA, X=X, y=y)
    print(f"toplanan örnek: {len(y)} ({len(y) // 4} karar)", flush=True)
    n = len(drop_count := [0, 0, 0, 0])
    y = y - y.reshape(-1, n).mean(axis=1).repeat(n)      # her kararın kendi ortalamasından fark

    best = None
    for ridge in RIDGES:
        agent = LearnedStation(ridge=ridge, extended=True, maximize=True)
        agent.X, agent.y = list(X), list(y)
        agent.fit()
        agent.X, agent.y = [], []
        jobs = [(r, s) for r in RATES for s in VAL_SEEDS]
        with ProcessPoolExecutor() as pool:
            res = list(pool.map(_val, [(agent.weights.tolist(), agent.mean.tolist(), agent.std.tolist(), r, s)
                                       for r, s in jobs]))
        thr = sum(r[0] for r in res) / len(res)
        ct = sum(r[1] for r in res) / len(res)
        print(f"doğrulama ridge={ridge}: throughput {thr:.2f}, sipariş süresi {ct:.1f}", flush=True)
        if best is None or thr > best[0]:
            best = (thr, ridge, agent)
    agent = best[2]
    agent.X, agent.y = list(X), list(y)
    agent.save(ROOT / "models" / "station_policy_v2.json")
    print(f"seçilen ridge={best[1]} -> models/station_policy_v2.json")


def _val(args):
    weights, mean, std, rate, seed = args
    agent = LearnedStation(extended=True, maximize=True)
    agent.weights, agent.mean, agent.std = np.array(weights), np.array(mean), np.array(std)
    return validate(agent, rate, seed)


if __name__ == "__main__":
    main()
