"""WHCA* öncelik sırası için doğrusal puanı CEM (çapraz entropi yöntemi) ile öğrenir.

    uv run python tools/train_priority.py

Her robotun puanı w · (özellikler / ölçek) ile hesaplanır ve puanı yüksek olan önce planlanır.
Her turda normal dağılımdan aday w'ler çekilir ve simülasyonda denenir. Sonra en iyi adaylara
göre dağılımın ortalaması ve sapması güncellenir. Amaç ortalama throughput'u artırmak.
Bir turdaki bütün adaylar aynı seed'lerle denenir. Eğitimde 1000-1099, doğrulamada 2000-2009
seed'leri kullanılır. Test seed'leri (0-29) burada kullanılmaz. Geri kalan her şey aynı, hepsinde
WHCA* + açık artırma + öğrenilmiş istasyon seçici (v1) kullanılıyor.
Ağırlıklar models/priority_policy.json, eğitim kaydı results/priority_training.csv dosyasına yazılır.
"""

from __future__ import annotations

import csv
import json
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.priority import FEATURES, LinearPriority, heuristic
from warehouse_mapf.sim import Simulation
from warehouse_mapf.stations import LearnedStation
from warehouse_mapf.warehouse import generate_warehouse

ROOT = Path(__file__).resolve().parent.parent
WARMUP, HORIZON = 200, 1000
ROBOTS, DENSITY = 30, "medium"
RATES = [0.6, 0.8]
SCALE = np.array([1, 1, 20, 20, 5, 3, 10], dtype=float)   # özelliklerin tipik büyüklüğü
POP, ELITE, ITERS, SEEDS_PER_ITER = 24, 6, 12, 6
VAL_SEEDS = range(2000, 2010)


def evaluate(args) -> float:
    weights, rate, seed = args
    warehouse = generate_warehouse(density=DENSITY)
    orders = generate_orders(warehouse, rate, WARMUP + HORIZON, random.Random(seed))
    priority = None if weights is None else LinearPriority(np.asarray(weights) / SCALE)
    m = Simulation(warehouse, orders, ROBOTS, greedy_assign, horizon=HORIZON, warmup=WARMUP, seed=seed,
                   planner="windowed", allocation="auction", priority=priority,
                   station=LearnedStation.load(ROOT / "models" / "station_policy.json")).run()
    return m.throughput


def score(pool, candidates, seeds) -> list[float]:
    jobs = [(w, RATES[k % len(RATES)], s) for w in candidates for k, s in enumerate(seeds)]
    res = list(pool.map(evaluate, jobs))
    n = len(seeds)
    return [float(np.mean(res[i * n:(i + 1) * n])) for i in range(len(candidates))]


def main() -> None:
    rng = np.random.default_rng(0)
    dim = len(FEATURES)
    mean, std = np.zeros(dim), np.full(dim, 2.0)
    log = []
    with ProcessPoolExecutor() as pool:
        for it in range(ITERS):
            seeds = [1000 + (it * SEEDS_PER_ITER + k) % 100 for k in range(SEEDS_PER_ITER)]
            cands = [mean.tolist()] + [(mean + std * rng.standard_normal(dim)).tolist() for _ in range(POP - 1)]
            fitness = score(pool, cands, seeds)
            order = np.argsort(fitness)[::-1]
            elite = np.array([cands[i] for i in order[:ELITE]])
            mean = elite.mean(axis=0)
            std = elite.std(axis=0) + 0.05                 # sapma sıfıra inmesin, arama dursun istemiyoruz
            log.append({"iter": it, "best": max(fitness), "mean_candidate": fitness[0],
                        "median": float(np.median(fitness)), **{f: round(v, 3) for f, v in zip(FEATURES, mean)}})
            print(f"tur {it + 1}/{ITERS}: en iyi {max(fitness):.2f}, ortalama aday {fitness[0]:.2f}, "
                  f"ağırlıklar {np.round(mean, 2).tolist()}", flush=True)

        # doğrulamada öğrenilen ağırlıklar, rastgele sıra ve kural tabanlı sıra karşılaştırılır
        val = {}
        candidates = {"learned": mean.tolist(), "random": None,
                      "carrying-first": (heuristic("carrying-first").weights * SCALE).tolist()}
        for name, w in candidates.items():
            val[name] = score(pool, [w], list(VAL_SEEDS))[0]
            print(f"doğrulama {name}: throughput {val[name]:.2f}", flush=True)

    (ROOT / "models" / "priority_policy.json").write_text(json.dumps(
        {"features": FEATURES, "scale": SCALE.tolist(), "weights": mean.tolist(), "validation": val}, indent=1))
    with (ROOT / "results" / "priority_training.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(log[0]))
        writer.writeheader()
        writer.writerows(log)


if __name__ == "__main__":
    main()
