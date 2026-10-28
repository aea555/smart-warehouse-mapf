"""Öğrenen istasyon seçiciyi eğitir. Karşılaştırdığımız kuralın alpha'sını da burada seçer.

    uv run python tools/train_station.py              # v1
    uv run python tools/train_station.py --extended   # v1x, birkaç durum özelliği daha var

Önce 1000-1039 seed'leriyle eğitim yapılır. Ajan ε-greedy seçimle veri toplar ve her simülasyondan
sonra model yeniden eğitilir. Sonra 2000-2009 seed'leriyle ridge katsayısı ve kuralın alpha'sı seçilir.
Seçilen model models/station_policy.json dosyasına, öğrenme eğrisi ve doğrulama sonuçları
results/station_training.csv dosyasına yazılır.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.sim import Simulation
from warehouse_mapf.stations import LearnedStation, QueueAwareStation
from warehouse_mapf.warehouse import generate_warehouse

ROOT = Path(__file__).resolve().parent.parent
WARMUP, HORIZON = 200, 1000
ROBOTS, DENSITY = 30, "medium"
RATES = [0.45, 0.6, 0.8]
TRAIN_SEEDS = range(1000, 1040)
VAL_SEEDS = range(2000, 2010)
RIDGES = [0.1, 1.0, 10.0, 100.0]
ALPHAS = [0, 2, 4, 6, 8, 12, 16]


def simulate(seed: int, rate: float, station) -> float:
    warehouse = generate_warehouse(density=DENSITY)
    orders = generate_orders(warehouse, rate, WARMUP + HORIZON, random.Random(seed))
    sim = Simulation(warehouse, orders, ROBOTS, greedy_assign, horizon=HORIZON, warmup=WARMUP,
                     seed=seed, planner="windowed", allocation="auction", station=station)
    return sim.run()


def validate(make_station) -> dict:
    """Doğrulama seed'lerinde üç yük için ortalama throughput ve sipariş süresi."""
    thr, ct = [], []
    for rate in RATES:
        for seed in VAL_SEEDS:
            m = simulate(seed, rate, make_station())
            thr.append(m.throughput)
            ct.append(m.mean_completion_time)
    return {"throughput": sum(thr) / len(thr), "completion_time": sum(ct) / len(ct)}


EXTENDED = "--extended" in sys.argv       # v1x'te ödül aynı, duruma yoldaki robotlar ve genel yük eklenir
SUFFIX = "_v1x" if EXTENDED else ""


def main() -> None:
    log = []

    # 1) eğitim, ε 0,3'ten 0,05'e iner
    agent = LearnedStation(epsilon=0.3, seed=1, extended=EXTENDED)
    for k, seed in enumerate(TRAIN_SEEDS):
        agent.epsilon = max(0.05, 0.3 * (1 - k / len(TRAIN_SEEDS)))
        rate = RATES[k % len(RATES)]
        m = simulate(seed, rate, agent)
        agent.fit()
        log.append({"stage": "train", "episode": k, "seed": seed, "rate": rate,
                    "epsilon": round(agent.epsilon, 3), "throughput": m.throughput,
                    "completion_time": round(m.mean_completion_time, 1), "samples": len(agent.y)})
        print(f"eğitim {k + 1}/{len(TRAIN_SEEDS)}  hız {rate}  ε={agent.epsilon:.2f}  thr={m.throughput:.1f}  "
              f"veri={len(agent.y)}", flush=True)

    # 2) ridge katsayısı doğrulama seed'leriyle seçilir, model hep aynı eğitim verisiyle eğitilir
    best = None
    for ridge in RIDGES:
        agent.ridge = ridge
        agent.fit()
        frozen = LearnedStation(epsilon=0.0, extended=EXTENDED)
        frozen.weights, frozen.mean, frozen.std = agent.weights, agent.mean, agent.std
        res = validate(lambda: _copy(frozen))
        log.append({"stage": "val-learned", "ridge": ridge, **res})
        print(f"doğrulama ridge={ridge}: {res}", flush=True)
        if best is None or res["throughput"] > best[0]["throughput"]:
            best = (res, ridge)
    agent.ridge = best[1]
    agent.fit()
    agent.save(ROOT / "models" / f"station_policy{SUFFIX}.json")
    if EXTENDED:
        print(f"seçilen ridge={best[1]}")
        return

    # 3) kuralın alpha'sı doğrulama seed'leriyle seçilir
    best_alpha = None
    for alpha in ALPHAS:
        res = validate(lambda: QueueAwareStation(alpha))
        log.append({"stage": "val-rule", "alpha": alpha, **res})
        print(f"doğrulama alpha={alpha}: {res}", flush=True)
        if best_alpha is None or res["throughput"] > best_alpha[0]["throughput"]:
            best_alpha = (res, alpha)
    (ROOT / "models" / "station_rule.json").write_text(json.dumps({"alpha": best_alpha[1]}))

    keys = sorted({k for row in log for k in row})
    with (ROOT / "results" / f"station_training{SUFFIX}.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(log)
    print(f"seçilen ridge={best[1]}, seçilen alpha={best_alpha[1]}")


def _copy(agent: LearnedStation) -> LearnedStation:
    c = LearnedStation(epsilon=0.0, extended=agent.extended)
    c.weights, c.mean, c.std = agent.weights, agent.mean, agent.std
    return c


if __name__ == "__main__":
    main()
