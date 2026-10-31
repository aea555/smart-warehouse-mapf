"""results/final.csv'den final grafiklerini ve özet tabloyu üretir.

    uv run --group analysis python tools/plot_final.py

Her düzende en çok robotlu durumun kapasite eğrisi docs/media/final_capacity.png dosyasına çizilir.
Düzen, robot sayısı, hız ve politikaya göre ortalamalar results/final_summary.csv dosyasına yazılır.
Bir de seçili yüklerde P3 ile P2, P3 ile P3-rule arasındaki farkı (%95 güven aralığıyla) yazdırır.
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
CSV = ROOT / "results" / "final.csv"
OUT = ROOT / "docs" / "media" / "final_capacity.png"
SUMMARY = ROOT / "results" / "final_summary.csv"

STYLE = {
    "P0": {"label": "P0 bağımsız A* + Local Repair", "color": "#d1495b"},
    "P1": {"label": "P1 WHCA*", "color": "#2e86ab"},
    "P2": {"label": "P2 + açık artırma", "color": "#edae49"},
    "P3-rule": {"label": "P3 (kural) + istasyon ve öncelik kuralı", "color": "#66a182"},
    "P3": {"label": "P3 + öğrenen istasyon ve öncelik", "color": "#3d2b56"},
}
TITLES = {"low": "Düşük raf yoğunluğu", "medium": "Orta raf yoğunluğu (eğitim)",
          "high": "Yüksek raf yoğunluğu", "movingai": "MovingAI warehouse-10-20-10-2-1"}
# özet tablodaki yük noktaları (düzen, robot, hız)
POINTS = [("low", 30, 0.6), ("medium", 30, 0.6), ("high", 30, 0.6),
          ("low", 30, 0.8), ("medium", 30, 0.8), ("high", 30, 0.8),
          ("movingai", 100, 0.8), ("movingai", 100, 1.2)]


def paired(groups, key_a, key_b, metric):
    """Aynı seed'leri eşleştirip a - b farkının ortalamasını, %95 güven aralığının yarısını ve b'nin ortalamasını döndürür."""
    a = {r["seed"]: float(r[metric]) for r in groups[key_a]}
    b = {r["seed"]: float(r[metric]) for r in groups[key_b]}
    d = [a[s] - b[s] for s in a if s in b]
    half = 1.96 * st.stdev(d) / len(d) ** 0.5 if len(d) > 1 else 0.0
    return st.mean(d), half, st.mean(b.values())


def main() -> None:
    groups = defaultdict(list)
    for row in csv.DictReader(CSV.open()):
        groups[(row["layout"], int(row["robots"]), float(row["rate"]), row["policy"])].append(row)
    layouts = [lay for lay in TITLES if any(k[0] == lay for k in groups)]

    # özet CSV
    with SUMMARY.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["layout", "robots", "rate", "policy", "runs", "throughput", "throughput_sd",
                         "completion_time", "conflicts", "deadlocked_pct"])
        for (lay, n, r, p), rows in sorted(groups.items()):
            thr = [float(x["throughput"]) for x in rows]
            writer.writerow([lay, n, r, p, len(rows), round(st.mean(thr), 2), round(st.stdev(thr), 2),
                             round(st.mean(float(x["mean_completion_time"]) for x in rows), 1),
                             round(st.mean(int(x["conflicts"]) for x in rows), 1),
                             round(100 * st.mean(int(x["deadlocked"]) for x in rows), 1)])

    # grafik
    fig, axes = plt.subplots(1, len(layouts), figsize=(4.3 * len(layouts), 4.4))
    for ax, lay in zip(axes, layouts):
        n = max(k[1] for k in groups if k[0] == lay)
        rates = sorted({k[2] for k in groups if k[0] == lay and k[1] == n})
        demand = [100 * r for r in rates]
        ax.plot(demand, demand, "--", color="#888888", lw=1, label="talep")
        for policy, style in STYLE.items():
            means, sds = [], []
            for r in rates:
                thr = [float(x["throughput"]) for x in groups[(lay, n, r, policy)]]
                means.append(st.mean(thr))
                sds.append(st.stdev(thr))
            ax.plot(demand, means, "o-", color=style["color"], lw=2, ms=3.5, label=style["label"])
            ax.fill_between(demand, [m - s for m, s in zip(means, sds)], [m + s for m, s in zip(means, sds)],
                            color=style["color"], alpha=0.12)
        seeds = len(groups[(lay, n, rates[0], "P0")])
        ax.set_title(f"{TITLES[lay]}\n{n} robot, {seeds} seed", fontsize=10.5)
        ax.set_xlabel("Gelen sipariş (100 adımda)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Throughput (100 adımda tamamlanan)")
    axes[0].legend(fontsize=7.5, loc="upper left")
    fig.suptitle("Kapasite eğrileri (ortalama ± standart sapma). Öğrenen modeller yalnızca orta yoğunlukta eğitildi.",
                 fontsize=11)
    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160)
    print(f"-> {OUT}\n-> {SUMMARY}\n")

    # eşleştirilmiş farklar
    print(f"{'nokta':<22}{'metrik':<12}{'P2':>8}{'P3-P2':>18}{'P3-rule':>9}{'P3-P3rule':>18}")
    for lay, n, r in POINTS:
        if (lay, n, r, "P3") not in groups:
            continue
        for metric, label in (("throughput", "throughput"), ("mean_completion_time", "süre")):
            d1, h1, base2 = paired(groups, (lay, n, r, "P3"), (lay, n, r, "P2"), metric)
            d2, h2, base_rule = paired(groups, (lay, n, r, "P3"), (lay, n, r, "P3-rule"), metric)
            print(f"{f'{lay} {n}r {r}':<22}{label:<12}{base2:>8.1f}{f'{d1:+.1f} ±{h1:.1f}':>18}"
                  f"{base_rule:>9.1f}{f'{d2:+.1f} ±{h2:.1f}':>18}")


if __name__ == "__main__":
    main()
