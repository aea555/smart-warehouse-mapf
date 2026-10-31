"""RQ2 deneyi. Bir koridor kapanınca ya da robotlar arızalanınca politikaların nasıl davrandığına bakar.

    uv run python tools/run_rq2.py

Olaylar 500. adımda başlar ve 300 adım sürer. Isınma 200, ölçüm 1000 adım.
Her simülasyonun özeti results/rq2.csv dosyasına yazılır. Grafik için 50 adımlık dilimlerde
tamamlanan sipariş sayıları da results/rq2_timeseries.csv dosyasına yazılır.
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
from warehouse_mapf.priority import LinearPriority, heuristic
from warehouse_mapf.sim import Event, Simulation
from warehouse_mapf.stations import LearnedStation, QueueAwareStation
from warehouse_mapf.warehouse import generate_warehouse

WARMUP, HORIZON = 200, 1000
EVENT_START, EVENT_LEN = 500, 300
SEEDS = range(30)
ROBOTS = 30
DENSITY = "medium"
RATES = [0.45, 0.6]
BIN = 50

BLOCK = tuple((x, 10) for x in range(14, 26))     # deponun ortasındaki yatay koridordan 12 hücre
SCENARIOS = {
    "none": (),
    "block": (Event("block", EVENT_START, EVENT_LEN, cells=BLOCK),),
    "fail": (Event("fail", EVENT_START, EVENT_LEN, count=5),),
    "both": (Event("block", EVENT_START, EVENT_LEN, cells=BLOCK),
             Event("fail", EVENT_START, EVENT_LEN, count=5)),
}
POLICIES = {
    "P0": dict(),
    "P1": dict(planner="windowed"),
    "P1+replan": dict(planner="windowed", event_replan=True),
    "P2-auction": dict(planner="windowed", allocation="auction"),
    "P2": dict(planner="windowed", allocation="auction", event_replan=True),
    "P3-rule": dict(planner="windowed", allocation="auction", event_replan=True),   # + kural tabanlı istasyon ve öncelik
    "P3": dict(planner="windowed", allocation="auction", event_replan=True),        # + öğrenilmiş istasyon ve öncelik
}

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def make_extras(policy: str) -> dict:
    """P3'ün istasyon ve öncelik nesneleri durum tutuyor, o yüzden her simülasyonda yeniden kuruluyor."""
    if policy == "P3-rule":
        alpha = json.loads((ROOT / "models" / "station_rule.json").read_text())["alpha"]
        return {"station": QueueAwareStation(alpha), "priority": heuristic("carrying-first")}
    if policy == "P3":
        data = json.loads((ROOT / "models" / "priority_policy.json").read_text())
        return {"station": LearnedStation.load(ROOT / "models" / "station_policy.json"),
                "priority": LinearPriority(np.array(data["weights"]) / np.array(data["scale"]), name="learned")}
    return {}


def summarize(sim: Simulation) -> dict:
    steps, times = sim.completion_steps, sim.completion_times
    def rate(a, b):           # [a, b) aralığında 100 adım başına tamamlanan sipariş
        return 100 * sum(a <= s < b for s in steps) / (b - a)
    before = rate(WARMUP, EVENT_START)
    during = rate(EVENT_START, EVENT_START + EVENT_LEN)
    after = rate(EVENT_START + EVENT_LEN, WARMUP + HORIZON)
    # toparlanma anı, son 100 adımdaki hızın ilk kez olay öncesinin %90'ına çıktığı adım
    recovery = None
    for t in range(EVENT_START + 100, WARMUP + HORIZON + 1):
        if rate(t - 100, t) >= 0.9 * before:
            recovery = t - EVENT_START
            break
    # olay sürerken gelen siparişlerin tamamlanma süresi
    arrived_during = [ct for s, ct in zip(steps, times)
                      if EVENT_START <= s + 1 - ct < EVENT_START + EVENT_LEN]
    return {
        "before": round(before, 2), "during": round(during, 2), "after": round(after, 2),
        "drop_pct": round(100 * (1 - during / before), 1) if before else None,
        "recovery_steps": recovery if recovery is not None else WARMUP + HORIZON - EVENT_START,
        "recovered": int(recovery is not None),
        "ct_event_orders": round(sum(arrived_during) / len(arrived_during), 1) if arrived_during else None,
    }


def run_one(job):
    policy, scenario, rate, seed = job
    warehouse = generate_warehouse(density=DENSITY)
    orders = generate_orders(warehouse, rate, WARMUP + HORIZON, random.Random(seed))
    sim = Simulation(warehouse, orders, ROBOTS, greedy_assign, horizon=HORIZON, warmup=WARMUP,
                     seed=seed, events=SCENARIOS[scenario], **POLICIES[policy], **make_extras(policy))
    m = sim.run()
    row = {"policy": policy, "scenario": scenario, "rate": rate, "seed": seed,
           "throughput": m.throughput, "mean_completion_time": round(m.mean_completion_time, 1),
           "conflicts": m.conflicts, "deadlocked": m.deadlocked, **summarize(sim)}
    bins = [0] * ((WARMUP + HORIZON) // BIN)
    for s in sim.completion_steps:
        bins[s // BIN] += 1
    series = [{"policy": policy, "scenario": scenario, "rate": rate, "seed": seed,
               "step": i * BIN, "completed": c} for i, c in enumerate(bins)]
    return row, series


def main() -> None:
    jobs = [(p, sc, r, s) for p in POLICIES for sc in SCENARIOS for r in RATES for s in SEEDS]
    rows, series = [], []
    with ProcessPoolExecutor() as pool:
        for row, ser in pool.map(run_one, jobs, chunksize=4):
            rows.append(row)
            series.extend(ser)
    RESULTS.mkdir(exist_ok=True)
    for name, data in (("rq2.csv", rows), ("rq2_timeseries.csv", series)):
        with (RESULTS / name).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    print(f"{len(rows)} simülasyon -> {RESULTS / 'rq2.csv'}")


if __name__ == "__main__":
    main()
