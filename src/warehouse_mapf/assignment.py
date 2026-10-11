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
    orders_copy = orders.copy() 
    orders_copy.reverse()
    robot_copy = available.copy()
    order_robot_dict: dict[int, int] = {}
    while orders_copy and robot_copy:
        current_item = orders_copy.pop()
        best_robot_id = None
        best_dist = None
        for robot_id, cell in sorted(robot_copy.items()):
            dist = manhattan(cell, current_item.pick) 
            if (best_dist is None) or (dist < best_dist): 
                best_dist = dist
                best_robot_id = robot_id
        del robot_copy[best_robot_id]
        order_robot_dict[current_item.id] = best_robot_id

    return order_robot_dict