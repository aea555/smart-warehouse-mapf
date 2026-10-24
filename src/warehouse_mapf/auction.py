"""Sıralı tek kalem açık artırma (SSI).

1. Her robot her siparişe teklif verir.
   Teklif = robotun boşalacağı adım + boşalacağı yerden rafa mesafe.
2. En düşük teklif o siparişi kazanır.
3. Kazanan robotun boşalma zamanı ve yeri güncellenir, teklifleri yeniden hesaplanır.
4. Sipariş ya da robot kalmayana kadar devam edilir.

Teklif boşalma zamanını da içerdiği için işini bitirmek üzere olan robot da teklif verebilir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .grid import Cell
from .orders import Order


@dataclass
class Bidder:
    robot: int
    free_in: int       # kaç adım sonra yeni bir siparişe başlayabilir
    pos: Cell          # o anda nerede olacak
    slots: int         # daha kaç sipariş alabilir


def auction(bidders: list[Bidder], orders: list[Order],
            dist: Callable[[Cell, Cell], int]) -> list[tuple[int, int]]:
    """(sipariş id, robot id) çiftlerini atanma sırasıyla döndürür.

    Eşitlikte önce gelen sipariş, sonra küçük id'li robot kazanır.
    """
    bidders = [Bidder(b.robot, b.free_in, b.pos, b.slots) for b in bidders if b.slots > 0]
    remaining = list(orders)

    def bid(b: Bidder, o: Order) -> int:
        return b.free_in + dist(b.pos, o.pick)

    # table[i][j], i. robotun j. siparişe verdiği teklif
    table = [[bid(b, o) for o in remaining] for b in bidders]
    result: list[tuple[int, int]] = []
    while bidders and remaining:
        best = None
        for i, b in enumerate(bidders):
            for j, o in enumerate(remaining):
                key = (table[i][j], o.arrival, o.id, b.robot)
                if best is None or key < best[0]:
                    best = (key, i, j)
        _, i, j = best
        b, o = bidders[i], remaining[j]
        result.append((o.id, b.robot))

        # kazanan robot bu siparişi teslim ettiği yerde ve o kadar adım sonra boşalır
        b.free_in = table[i][j] + dist(o.pick, o.drop)
        b.pos = o.drop
        b.slots -= 1
        del remaining[j]
        for row in table:
            del row[j]
        if b.slots == 0:
            del bidders[i]
            del table[i]
        else:
            table[i] = [bid(b, x) for x in remaining]
    return result
