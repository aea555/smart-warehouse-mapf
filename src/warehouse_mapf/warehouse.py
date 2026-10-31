"""Depo haritası.

- Raflar iki hücre kalınlığında yatay bantlar. Bantların arasında birer koridor var.
- Bantlar belli aralıklarla dikey geçitlerle bölünüyor.
- En alt satır park yeri, paketleme istasyonları sağ duvarda.
- Yoğunluğu iki geçit arasındaki raf sayısı belirliyor.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grid import Cell, Grid

# iki dikey geçit arasındaki raf sayısı
SHELF_BLOCK = {"low": 3, "medium": 5, "high": 8}


@dataclass
class Warehouse:
    grid: Grid
    pick_cells: list[Cell]   # rafın hemen üstündeki ya da altındaki koridor hücreleri
    drop_cells: list[Cell]   # paketleme istasyonlarının önündeki hücreler
    park_cells: list[Cell]   # robotların başladığı ve boşken beklediği yerler


def generate_warehouse(width: int = 36, height: int = 21, density: str = "medium",
                       drop_count: int = 4) -> Warehouse:
    block = SHELF_BLOCK[density]
    shelves: set[Cell] = set()
    # raf bantları y = 2-3, 5-6, 8-9 ..., aralarında birer koridor satırı
    for top in range(2, height - 3, 3):
        x = 2
        while x < width - 3:
            for dx in range(block):
                if x + dx < width - 3:
                    shelves.add((x + dx, top))
                    shelves.add((x + dx, top + 1))
            x += block + 1

    # istasyon masası sağ duvarda ve engel sayılır, teslimat masanın solundaki hücrede yapılır
    step = (height - 2) // (drop_count + 1)
    stations = {(width - 1, 1 + step * (i + 1)) for i in range(drop_count)}
    grid = Grid(width, height, shelves | stations)

    park_cells = [(x, height - 1) for x in range(1, width - 3)]
    drop_cells = sorted((x - 1, y) for (x, y) in stations)

    reserved = set(park_cells) | set(drop_cells)
    pick_cells = sorted({
        (x, y + dy)
        for (x, y) in shelves
        for dy in (-1, 1)
        if grid.is_free((x, y + dy)) and (x, y + dy) not in reserved
    })
    return Warehouse(grid, pick_cells, drop_cells, park_cells)


def load_movingai(path, stations_per_side: int = 4, park_step: int = 3) -> Warehouse:
    """MovingAI'daki warehouse haritalarından birini okuyup depo kurar.

    İstasyonlar sol ve sağ duvarda. Toplama hücreleri rafların hemen altı ve üstü.
    Park yerleri rafların iki yanındaki boş alanda, park_step hücre aralıkla.
    """
    from pathlib import Path

    lines = Path(path).read_text().splitlines()
    height = int(lines[1].split()[1])
    width = int(lines[2].split()[1])
    rows = lines[4:4 + height]
    blocked = {(x, y) for y, row in enumerate(rows) for x, ch in enumerate(row[:width]) if ch not in ".G"}

    # raflar, dış duvar hariç en soldaki ve en sağdaki engelin arasında
    inner = [x for (x, y) in blocked if 0 < x < width - 1 and 0 < y < height - 1]
    shelf_left, shelf_right = min(inner), max(inner)

    step = (height - 2) // (stations_per_side + 1)
    station_rows = [1 + step * (i + 1) for i in range(stations_per_side)]
    stations = {(0, y) for y in station_rows} | {(width - 1, y) for y in station_rows}
    drop_cells = sorted([(1, y) for y in station_rows] + [(width - 2, y) for y in station_rows])

    park_cells = sorted(
        (x, y)
        for y in range(2, height - 2, park_step)
        for x in [*range(4, shelf_left - 2, park_step), *range(shelf_right + 3, width - 4, park_step)]
        if (x, y) not in blocked
    )
    grid = Grid(width, height, blocked)
    reserved = set(park_cells) | set(drop_cells)
    pick_cells = sorted({
        (x, y + dy)
        for (x, y) in blocked
        if shelf_left <= x <= shelf_right and 0 < y < height - 1
        for dy in (-1, 1)
        if grid.is_free((x, y + dy)) and (x, y + dy) not in reserved
    })
    return Warehouse(grid, pick_cells, drop_cells, park_cells)
