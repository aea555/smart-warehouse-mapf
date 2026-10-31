"""results/rq2_timeseries.csv'den RQ2 grafiğini çizer.

    uv run --group analysis python tools/plot_rq2.py

Her panel bir yük ve bir senaryo. Çizgiler 30 seed'in ortalaması. Gri bant olayın sürdüğü aralık.
Grafik docs/media/rq2.png dosyasına kaydedilir.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "results" / "rq2_timeseries.csv"
OUT = ROOT / "docs" / "media" / "rq2.png"
BIN, WARMUP, EVENT_START, EVENT_LEN = 50, 200, 500, 300

STYLE = {
    "P0": ("P0: bağımsız A*", "#d1495b", "-"),
    "P1": ("P1: WHCA*, greedy", "#9a8c98", "-"),
    "P1+replan": ("P1 + olay anında yeniden planlama", "#9a8c98", "--"),
    "P2-auction": ("WHCA* + açık artırma", "#2e86ab", "--"),
    "P2": ("P2: açık artırma + yeniden planlama", "#2e86ab", "-"),
    "P3-rule": ("P3-kural: + istasyon ve öncelik kuralı", "#66a182", "--"),
    "P3": ("P3: + öğrenen istasyon ve öncelik", "#3d2b56", "-"),
}
SCENARIOS = {"block": "Koridor blokajı", "fail": "5 robot arızası", "both": "Blokaj + arıza"}


def main() -> None:
    data = defaultdict(lambda: defaultdict(list))
    for row in csv.DictReader(CSV.open()):
        key = (row["policy"], row["scenario"], float(row["rate"]))
        data[key][int(row["step"])].append(int(row["completed"]))
    rates = sorted({k[2] for k in data})

    fig, axes = plt.subplots(len(rates), len(SCENARIOS), figsize=(15, 4.2 * len(rates)),
                             sharex=True, squeeze=False)
    for i, rate in enumerate(rates):
        for j, (scenario, title) in enumerate(SCENARIOS.items()):
            ax = axes[i][j]
            ax.axvspan(EVENT_START, EVENT_START + EVENT_LEN, color="#cccccc", alpha=0.4, lw=0)
            for policy, (label, color, ls) in STYLE.items():
                series = data[(policy, scenario, rate)]
                steps = sorted(s for s in series if s >= WARMUP)
                ys = [100 * sum(series[s]) / len(series[s]) / BIN for s in steps]
                ax.plot([s + BIN / 2 for s in steps], ys, ls, color=color, lw=2, label=label)
            ax.set_title(f"{title} · {100 * rate:.0f} sipariş / 100 adım", fontsize=11)
            ax.grid(alpha=0.3)
            if j == 0:
                ax.set_ylabel("Throughput\n(100 adımda tamamlanan)")
            if i == len(rates) - 1:
                ax.set_xlabel("Adım (gri bant: olay süresi)")
    axes[0][0].legend(fontsize=8, loc="lower left")
    fig.suptitle("RQ2: olay altında throughput (30 robot, 30 seed ortalaması)", fontsize=13)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=150)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
