"""Depo üreteci, sipariş akışı ve simülasyon altyapısı testleri."""

import random
from pathlib import Path

import pytest

from warehouse_mapf.astar import find_path
from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.sim import Simulation
from warehouse_mapf.warehouse import generate_warehouse, load_movingai

MOVINGAI = Path(__file__).resolve().parent.parent / "maps" / "warehouse-10-20-10-2-1.map"


@pytest.mark.parametrize("density", ["low", "medium", "high"])
def test_all_special_cells_are_free_and_reachable(density):
    w = generate_warehouse(density=density)
    start = w.park_cells[0]
    for cell in w.pick_cells[::7] + w.drop_cells + w.park_cells[::5]:
        assert w.grid.is_free(cell)
        assert find_path(w.grid, start, cell) is not None


def test_density_changes_shelf_count():
    counts = [len(generate_warehouse(density=d).grid.blocked) for d in ("low", "medium", "high")]
    assert counts[0] < counts[1] < counts[2]


def test_orders_are_reproducible_and_sorted():
    w = generate_warehouse()
    a = generate_orders(w, 0.3, 500, random.Random(42))
    b = generate_orders(w, 0.3, 500, random.Random(42))
    assert a == b
    assert [o.arrival for o in a] == sorted(o.arrival for o in a)
    assert 100 < len(a) < 200   # beklenen yaklaşık 150


def test_single_robot_completes_orders_without_conflicts():
    w = generate_warehouse()
    orders = generate_orders(w, 0.005, 1000, random.Random(0))   # tek robot için az sipariş
    m = Simulation(w, orders, 1, greedy_assign, horizon=1000).run()
    assert m.conflicts == 0
    assert m.orders_completed >= m.orders_arrived - 1


def test_robots_never_share_a_cell_or_swap():
    w = generate_warehouse()
    orders = generate_orders(w, 0.3, 300, random.Random(1))
    sim = Simulation(w, orders, 20, greedy_assign, horizon=300)
    for _ in range(300):
        before = [r.pos for r in sim.robots]
        sim.step()
        after = [r.pos for r in sim.robots]
        assert len(set(after)) == len(after)
        for i in range(len(after)):
            for j in range(i + 1, len(after)):
                assert not (after[i] == before[j] and after[j] == before[i] and before[i] != before[j])


def test_movingai_map_roles_are_free_reachable_and_disjoint():
    w = load_movingai(MOVINGAI)
    assert (w.grid.width, w.grid.height) == (161, 63)
    assert len(w.drop_cells) == 8
    assert not set(w.pick_cells) & (set(w.park_cells) | set(w.drop_cells))
    start = w.park_cells[0]
    for cell in w.pick_cells[::50] + w.drop_cells + w.park_cells[::20]:
        assert w.grid.is_free(cell)
        assert find_path(w.grid, start, cell) is not None
