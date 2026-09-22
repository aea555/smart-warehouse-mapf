"""Depo zemini için ızgara modeli.

Hücreler ``(x, y)`` tuple'ı. ``x`` sağa, ``y`` aşağı doğru artar (ekran koordinatı).
"""

from __future__ import annotations

Cell = tuple[int, int]


class Grid:
    """Boş ve engelli hücrelerden oluşan bir depo katı."""

    def __init__(self, width: int, height: int, blocked: set[Cell] | None = None):
        self.width = width
        self.height = height
        self.blocked: set[Cell] = set(blocked or ())

    def in_bounds(self, cell: Cell) -> bool:
        """Hücre ızgaranın sınırları içinde mi?"""
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    def is_free(self, cell: Cell) -> bool:
        """Hücre hem sınırların içinde hem de engelsiz mi?"""
        return self.in_bounds(cell) and cell not in self.blocked

    def neighbors(self, cell: Cell) -> list[Cell]:
        """Geçilebilir komşuları döndürür. Robot yukarı, sağa, aşağı ve sola gidebilir, çapraz gidemez."""
        x, y = cell
        candidates = [(x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)]
        return [c for c in candidates if self.is_free(c)]

    @classmethod
    def from_text(cls, text: str) -> Grid:
        """Metin haritasından ızgara kurar. ``#`` engel, geri kalanı boş."""
        rows = [line.strip() for line in text.strip().splitlines()]
        width = max(len(row) for row in rows)
        blocked = {
            (x, y)
            for y, row in enumerate(rows)
            for x, ch in enumerate(row)
            if ch == "#"
        }
        return cls(width, len(rows), blocked)

    def to_text(
        self,
        path: list[Cell] | None = None,
        start: Cell | None = None,
        goal: Cell | None = None,
    ) -> str:
        """Izgarayı metne çevirir. ``S`` başlangıç, ``G`` hedef, ``o`` yol, ``#`` engel."""
        on_path = set(path or ())
        rows = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                cell = (x, y)
                if cell == start:
                    row.append("S")
                elif cell == goal:
                    row.append("G")
                elif cell in self.blocked:
                    row.append("#")
                elif cell in on_path:
                    row.append("o")
                else:
                    row.append(".")
            rows.append("".join(row))
        return "\n".join(rows)

    def __repr__(self) -> str:
        return f"Grid({self.width}x{self.height}, {len(self.blocked)} engel)"
