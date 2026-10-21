"""results/capacity.csv'den kapasite eğrisi grafiğini çizer.

    uv run --group analysis python tools/plot_capacity.py

Grafik docs/media/capacity.png dosyasına kaydedilir.

Üst sırada sipariş geliş hızına göre throughput var. Kesikli çizgi gelen talep.
Eğrinin kesikli çizgiden ayrıldığı nokta sistemin kapasitesi.
Alt sırada kalıcı kilitlenmeyle biten simülasyonların oranı var.
"""

from __future__ import annotations

import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "results" / "capacity.csv"
OUT = ROOT / "docs" / "media" / "capacity.png"

STYLE = {
    "P0": {"label": "P0: bağımsız A* (Local Repair)", "color": "#d1495b"},
    "P1-CA": {"label": "tam rotalı Cooperative A* (CA*)", "color": "#9a8c98"},
    "P1": {"label": "P1: WHCA* (pencereli Cooperative A*)", "color": "#2e86ab"},
}


def main() -> None:
    groups = defaultdict(list)
    for row in csv.DictReader(CSV.open()):
        groups[(row["policy"], int(row["robots"]), float(row["rate"]))].append(row)
    robot_counts = sorted({k[1] for k in groups})
    rates = sorted({k[2] for k in groups})

    fig, axes = plt.subplots(2, len(robot_counts), figsize=(4.2 * len(robot_counts), 6.4),
                             sharex=True, gridspec_kw={"height_ratios": [3, 1.3]})
    for col, n in enumerate(robot_counts):
        top, bottom = axes[0][col], axes[1][col]
        demand = [100 * r for r in rates]
        top.plot(demand, demand, "--", color="#888888", lw=1, label="talep (gelen sipariş)")
        for policy, style in STYLE.items():
            means, sds, dead = [], [], []
            for r in rates:
                rows = groups[(policy, n, r)]
                thr = [float(x["throughput"]) for x in rows]
                means.append(st.mean(thr))
                sds.append(st.stdev(thr) if len(thr) > 1 else 0.0)
                dead.append(100 * sum(int(x["deadlocked"]) for x in rows) / len(rows))
            lo = [m - s for m, s in zip(means, sds)]
            hi = [m + s for m, s in zip(means, sds)]
            top.plot(demand, means, "o-", color=style["color"], lw=2, ms=4, label=style["label"])
            top.fill_between(demand, lo, hi, color=style["color"], alpha=0.15)
            bottom.plot(demand, dead, "o-", color=style["color"], lw=2, ms=4)
        top.set_title(f"{n} robot", fontsize=12)
        top.grid(alpha=0.3)
        bottom.grid(alpha=0.3)
        bottom.set_ylim(-5, 105)
        bottom.set_xlabel("Gelen sipariş (100 adımda)")
        if col == 0:
            top.set_ylabel("Throughput\n(100 adımda tamamlanan)")
            bottom.set_ylabel("Kalıcı kilitlenen\nsimülasyon (%)")
            top.legend(fontsize=8, loc="upper left")

    fig.suptitle("Kapasite eğrisi: ortalama ± standart sapma, her nokta 10 seed (orta raf yoğunluğu)", fontsize=12)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
