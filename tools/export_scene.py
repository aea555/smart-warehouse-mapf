"""Demo senaryolarını üretir, find_path ile çözer ve Unity için JSON'a yazar.

    uv run python tools/export_scene.py

Her senaryoda raf düzeni, engeller ve hedef farklı. Yolu find_path bulur.
Bu dosya sadece tek robotlu ilk demo için. Deneylerdeki depolar warehouse.py'den geliyor.
Çıktı unity/Assets/StreamingAssets/scene.json dosyasına yazılır.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from warehouse_mapf.astar import find_path, manhattan
from warehouse_mapf.grid import Cell, Grid

WIDTH, HEIGHT = 28, 17
SCENARIO_COUNT = 24
OBSTACLE_RATE = 0.10        # koridor hücrelerinin yaklaşık %10'u engel
MIN_GOAL_DISTANCE = 18      # hedef başlangıçtan en az bu kadar uzakta olsun (manhattan)

OUT = Path(__file__).resolve().parent.parent / "unity" / "Assets" / "StreamingAssets" / "scene.json"


def generate_layout(rng: random.Random) -> tuple[set[Cell], set[Cell]]:
    """Raf bantlarını ve koridor engellerini üretir.

    Her bant 2 hücre yüksekliğinde. Raf blokları 2-5 hücre uzunluğunda, aralarında 1 hücre boşluk var.
    """
    shelves: set[Cell] = set()
    for top in range(1, HEIGHT - 2, 3):
        x = 1
        while x < WIDTH - 1:
            length = rng.randint(2, 5)
            for dx in range(length):
                if x + dx < WIDTH - 1:
                    shelves.add((x + dx, top))
                    shelves.add((x + dx, top + 1))
            x += length + 1

    obstacles = {
        (x, y)
        for y in range(HEIGHT)
        for x in range(WIDTH)
        if (x, y) not in shelves and rng.random() < OBSTACLE_RATE
    }
    return shelves, obstacles


def pick_goal(rng: random.Random, grid: Grid, shelves: set[Cell], start: Cell) -> Cell | None:
    """Hedef olarak bir rafın yanında, başlangıca uzak, boş bir hücre seçer."""
    candidates = [
        (x, y)
        for y in range(HEIGHT)
        for x in range(WIDTH)
        if grid.is_free((x, y))
        and manhattan((x, y), start) >= MIN_GOAL_DISTANCE
        and any((x + dx, y + dy) in shelves for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    ]
    return rng.choice(candidates) if candidates else None


def _xy(cell: Cell) -> dict[str, int]:
    return {"x": cell[0], "y": cell[1]}


def make_scenario(seed: int) -> dict | None:
    rng = random.Random(seed)
    shelves, obstacles = generate_layout(rng)

    start: Cell = (rng.randint(0, 3), HEIGHT - 1)          # alt koridordaki şarj istasyonu
    for c in (start, (start[0] + 1, start[1]), (start[0], start[1] - 1)):
        obstacles.discard(c)                               # istasyonun çevresi açık kalsın

    grid = Grid(WIDTH, HEIGHT, shelves | obstacles)
    goal = pick_goal(rng, grid, shelves, start)
    if goal is None:
        return None

    path = find_path(grid, start, goal)
    if path is None:
        return None                                        # hedefe yol yok, seed atlanır

    return {
        "seed": seed,
        "width": WIDTH,
        "height": HEIGHT,
        "shelves": [_xy(c) for c in sorted(shelves)],
        "obstacles": [_xy(c) for c in sorted(obstacles)],
        "start": _xy(start),
        "goal": _xy(goal),
        "path": [_xy(c) for c in path],
        "_grid": grid,
        "_path": path,
    }


def main() -> None:
    scenarios, skipped, seed = [], 0, 1
    while len(scenarios) < SCENARIO_COUNT:
        s = make_scenario(seed)
        if s is None:
            skipped += 1
        else:
            scenarios.append(s)
        seed += 1

    example = scenarios[0]
    start = (example["start"]["x"], example["start"]["y"])
    goal = (example["goal"]["x"], example["goal"]["y"])
    print(f"ornek senaryo (seed {example['seed']}):   # raf/engel   o rota   S baslangic   G hedef\n")
    print(example["_grid"].to_text(path=example["_path"], start=start, goal=goal))

    lengths = [len(s["_path"]) for s in scenarios]
    print(f"\n{len(scenarios)} senaryo uretildi ({skipped} seed ulasilamaz hedef yuzunden atlandi)")
    print(f"yol uzunlugu: en kisa {min(lengths)}, en uzun {max(lengths)}, ortalama {sum(lengths) / len(lengths):.1f} hucre")

    for s in scenarios:
        del s["_grid"], s["_path"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"scenarios": scenarios}, indent=1), encoding="utf-8")
    print(f"-> {OUT.relative_to(OUT.parents[3])}")


if __name__ == "__main__":
    main()
