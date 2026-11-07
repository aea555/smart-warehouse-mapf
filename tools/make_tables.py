"""Makaledeki tabloları results/ altındaki CSV'lerden üretir.

    uv run --group analysis python tools/make_tables.py [çıktı klasörü]

Her tablo ayrı bir .tex dosyasına yazılır (varsayılan klasör paper/tables).
Ondalıklar Türkçedeki gibi virgülle yazılır.
İki politikayı karşılaştırırken aynı seed'li simülasyonlar eşleştirilir. Fark için Wilcoxon
işaretli sıra testi ve etki büyüklüğü (Cohen d_z) hesaplanır.
"""

from __future__ import annotations

import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "paper" / "tables"
POLICIES = ["P0", "P1", "P2", "P3-rule", "P3"]
NAMES = {"P0": "P0", "P1": "P1", "P2": "P2", "P3-rule": "P3 (kural)", "P3": "P3"}


def num(x: float, d: int = 1) -> str:
    return f"{x:.{d}f}".replace(".", ",").replace("-", "$-$")


def load(name: str) -> list[dict]:
    return list(csv.DictReader((RES / name).open()))


def group(rows, *keys):
    g = defaultdict(list)
    for r in rows:
        g[tuple(r[k] for k in keys)].append(r)
    return g


def col(rows, metric):
    return [float(r[metric]) for r in rows]


def ms(values, d=1):
    return f"{num(st.mean(values), d)} $\\pm$ {num(st.stdev(values), d)}"


def paired(a_rows, b_rows, metric):
    a = {r["seed"]: float(r[metric]) for r in a_rows}
    b = {r["seed"]: float(r[metric]) for r in b_rows}
    d = [a[s] - b[s] for s in a if s in b]
    mean, sd = st.mean(d), st.stdev(d)
    half = 1.96 * sd / len(d) ** 0.5
    p = wilcoxon(d).pvalue if any(d) else 1.0
    dz = mean / sd if sd else 0.0
    return mean, half, p, dz, len(d)


def pval(p):
    return "$<$0,001" if p < 0.001 else num(p, 3)


def write(name: str, body: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.tex").write_text(body)
    print(f"-> {OUT / name}.tex")


# ana sonuçlar

POINTS = [("low", 30, 0.8), ("medium", 30, 0.6), ("medium", 30, 0.8), ("high", 30, 0.8),
          ("movingai", 100, 1.2)]
LAYOUT = {"low": "Düşük", "medium": "Orta", "high": "Yüksek", "movingai": "MovingAI"}


def main_table(final):
    """Tablodaki her hücreye throughput ortalaması ± standart sapma / ortalama teslim süresi yazılır."""
    g = group(final, "layout", "robots", "rate", "policy")
    head = " & ".join(f"{LAYOUT[l]}, {n} robot, {num(r)}" for l, n, r in POINTS)
    lines = []
    for p in POLICIES:
        cells = []
        for l, n, r in POINTS:
            rows = g[(l, str(n), str(r), p)]
            cells.append(f"{ms(col(rows, 'throughput'))} / {num(st.mean(col(rows, 'mean_completion_time')), 0)}")
        lines.append(f"{NAMES[p]} & " + " & ".join(cells) + r" \\")
    write("main", "\\begin{tabular}{l" + "c" * len(POINTS) + "}\n\\toprule\n"
          f"Yöntem & {head} \\\\\n\\midrule\n" + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")


def pairwise(final):
    g = group(final, "layout", "robots", "rate", "policy")
    pairs = [("P1", "P0"), ("P2", "P1"), ("P3", "P2"), ("P3", "P3-rule")]
    points = [("medium", 30, 0.8), ("movingai", 100, 1.2)]
    lines = []
    for l, n, r in points:
        for a, b in pairs:
            row = [f"{LAYOUT[l]}, {n} robot, {num(r)}" if (a, b) == pairs[0] else "", f"{NAMES[a]} $-$ {NAMES[b]}"]
            for metric, d in (("throughput", 1), ("mean_completion_time", 0)):
                mean, half, p, dz, _ = paired(g[(l, str(n), str(r), a)], g[(l, str(n), str(r), b)], metric)
                row += [f"{num(mean, d)} $\\pm$ {num(half, d)}", pval(p), num(dz, 1)]
            lines.append(" & ".join(row) + r" \\")
        lines.append(r"\midrule")
    lines.pop()
    write("pairwise", "\\begin{tabular}{llcccccc}\n\\toprule\n"
          " & & \\multicolumn{3}{c}{Throughput} & \\multicolumn{3}{c}{Teslim süresi} \\\\\n"
          "\\cmidrule(lr){3-5}\\cmidrule(lr){6-8}\n"
          "Nokta & Fark & Ort. $\\pm$ \\%95 GA & $p$ & $d_z$ & Ort. $\\pm$ \\%95 GA & $p$ & $d_z$ \\\\\n\\midrule\n"
          + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")


# RQ2

def rq2_table(rq2):
    g = group(rq2, "policy", "scenario", "rate")
    pols = ["P0", "P1", "P1+replan", "P2-auction", "P2", "P3-rule", "P3"]
    names = {"P1+replan": "P1 + olayda planlama", "P2-auction": "P1 + açık artırma", **NAMES}
    lines = []
    for p in pols:
        row = [names[p], ms(col(g[(p, "none", "0.6")], "throughput"))]
        for sc in ("block", "fail", "both"):
            rows = g[(p, sc, "0.6")]
            row.append(ms(col(rows, "during")))
            ct = [float(r["ct_event_orders"]) for r in rows if r["ct_event_orders"] not in ("", "None")]
            row.append(num(st.mean(ct), 0) if ct else "--")
        lines.append(" & ".join(row) + r" \\")
    write("rq2", "\\begin{tabular}{lccccccc}\n\\toprule\n"
          " & Olaysız & \\multicolumn{2}{c}{Koridor kapanması} & \\multicolumn{2}{c}{5 robot arızası} & \\multicolumn{2}{c}{İkisi birden} \\\\\n"
          "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\\cmidrule(lr){7-8}\n"
          "Yöntem & Throughput & Olay sırası & Süre & Olay sırası & Süre & Olay sırası & Süre \\\\\n\\midrule\n"
          + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")


# duyarlılık ve bileşenler

def sensitivity_table(sens):
    g = group(sens, "window", "rate")
    lines = []
    for w in ("4", "8", "16", "32"):
        row = [w]
        for r in ("0.45", "0.8"):
            rows = g[(w, r)]
            row += [ms(col(rows, "throughput")), num(st.mean(col(rows, "mean_wait_per_order")), 1),
                    num(st.mean(col(rows, "conflicts")), 0), num(st.mean(col(rows, "seconds")), 1)]
        lines.append(" & ".join(row) + r" \\")
    write("sensitivity", "\\begin{tabular}{lcccccccc}\n\\toprule\n"
          " & \\multicolumn{4}{c}{0,45 sipariş/adım} & \\multicolumn{4}{c}{0,8 sipariş/adım} \\\\\n"
          "\\cmidrule(lr){2-5}\\cmidrule(lr){6-9}\n"
          "Pencere & Throughput & Bekleme & Çakışma & sn & Throughput & Bekleme & Çakışma & sn \\\\\n\\midrule\n"
          + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")


def component_table(station, priority):
    gs = group(station, "selector", "robots", "rate")
    gp = group(priority, "priority", "robots", "rate")
    points = [("20", "0.6"), ("20", "0.8"), ("30", "0.6"), ("30", "0.8")]
    lines = []
    for label, g, key in (("Masa: siparişteki (rastgele)", gs, "random"), ("Masa: en yakın", gs, "nearest"),
                          ("Masa: kuyruk kuralı", gs, "rule"), ("Masa: öğrenen", gs, "learned"),
                          ("Sıra: rastgele", gp, "random"), ("Sıra: taşıyan önce", gp, "carrying-first"),
                          ("Sıra: öğrenen (CEM)", gp, "learned")):
        cells = []
        for n, r in points:
            rows = g[(key, n, r)]
            cells.append(f"{num(st.mean(col(rows, 'throughput')))} / {num(st.mean(col(rows, 'mean_completion_time')), 0)}")
        lines.append(f"{label} & " + " & ".join(cells) + r" \\")
        if key == "learned" and g is gs:
            lines.append(r"\midrule")
    write("components", "\\begin{tabular}{lcccc}\n\\toprule\n"
          "Bileşen & 20 robot, 0,6 & 20 robot, 0,8 & 30 robot, 0,6 & 30 robot, 0,8 \\\\\n\\midrule\n"
          + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")


def agitation_numbers(exp):
    for p in ("P0_no_agitation", "P0"):
        rows = [r for r in exp if r["policy"] == p]
        dead = sum(int(r["deadlocked"]) for r in rows)
        stalls = sum(int(r["stalls"]) for r in rows)
        solved = sum(int(r["stalls_resolved"]) for r in rows)
        print(f"{p}: kalıcı kilitlenme {dead}/{len(rows)}, tıkanma {stalls}, çözülen {solved}")


def main() -> None:
    final = load("final.csv")
    main_table(final)
    pairwise(final)
    rq2_table(load("rq2.csv"))
    sensitivity_table(load("sensitivity.csv"))
    component_table(load("station_test.csv"), load("priority_test.csv"))
    agitation_numbers(load("experiments.csv"))


if __name__ == "__main__":
    main()
