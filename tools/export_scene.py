"""Depo haritasını find_path ile çözer ve Unity için JSON'a yazar.

    uv run python tools/export_scene.py

Şimdilik tek bir sabit harita ve tek robot var. Python yolu bulur, Unity sadece çizer.
Çıktı unity/Assets/StreamingAssets/scene.json dosyasına yazılır.
"""

from __future__ import annotations

import json
from pathlib import Path

from warehouse_mapf.astar import find_path
from warehouse_mapf.grid import Cell, Grid

# # raf, . koridor
WAREHOUSE = """
....................
.##.##.##.##.##.##..
.##.##.##.##.##.##..
....................
.##.##.##.##.##.##..
.##.##.##.##.##.##..
....................
.##.##.##.##.##.##..
.##.##.##.##.##.##..
....................
"""

START: Cell = (0, 9)   # sol alt köşedeki şarj istasyonu
GOAL: Cell = (12, 1)   # bir rafın yanındaki hedef

OUT = Path(__file__).resolve().parent.parent / "unity" / "Assets" / "StreamingAssets" / "scene.json"


def _xy(cell: Cell) -> dict[str, int]:
    return {"x": cell[0], "y": cell[1]}


def main() -> None:
    grid = Grid.from_text(WAREHOUSE)
    path = find_path(grid, START, GOAL)

    scene = {
        "width": grid.width,
        "height": grid.height,
        "blocked": [_xy(c) for c in sorted(grid.blocked)],
        "start": _xy(START),
        "goal": _xy(GOAL),
        "hasPath": path is not None,
        "path": [_xy(c) for c in (path or [])],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(scene, indent=2), encoding="utf-8")

    print(grid.to_text(path=path, start=START, goal=GOAL))
    print()
    print(f"yol: {len(path) if path else 0} hücre  ->  {OUT.relative_to(OUT.parents[3])}")


if __name__ == "__main__":
    main()
