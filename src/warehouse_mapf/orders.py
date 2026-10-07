"""Sipariş üretimi.

Her siparişte robot raftan ürünü alıp paketleme istasyonuna götürür. Siparişler arasındaki süre
üstel dağılımdan çekilir, yani siparişler Poisson süreciyle gelir.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .grid import Cell
from .warehouse import Warehouse


@dataclass(frozen=True)
class Order:
    id: int
    arrival: int   # siparişin geldiği zaman adımı
    pick: Cell
    drop: Cell


def generate_orders(warehouse: Warehouse, rate: float, horizon: int,
                    rng: random.Random) -> list[Order]:
    """rate bir adımda ortalama kaç sipariş geldiğidir. Siparişler geliş sırasıyla döner."""
    orders: list[Order] = []
    t = rng.expovariate(rate)
    while t < horizon:
        orders.append(Order(
            id=len(orders),
            arrival=int(t),
            pick=rng.choice(warehouse.pick_cells),
            drop=rng.choice(warehouse.drop_cells),
        ))
        t += rng.expovariate(rate)
    return orders
