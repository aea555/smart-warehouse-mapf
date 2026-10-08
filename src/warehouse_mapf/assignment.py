"""Siparişleri robotlara atama politikaları."""

from __future__ import annotations

from .astar import manhattan
from .grid import Cell
from .orders import Order


def greedy_assign(available: dict[int, Cell], orders: list[Order]) -> dict[int, int]:
    """Siparişleri geliş sırasıyla en yakın boştaki robota verir (baseline).

    available robot id -> hücre sözlüğüdür. Dönen sözlük sipariş id -> robot id.
    Uzaklık rafa olan manhattan mesafesi, eşitlikte küçük id kazanır. Her robot en fazla
    bir sipariş alır, robot kalmazsa kalan siparişler atanmaz.
    """
    # TODO
    raise NotImplementedError
