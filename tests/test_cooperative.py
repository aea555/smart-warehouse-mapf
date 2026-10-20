"""Cooperative A* ve rezervasyon tablosu testleri."""

import random

import pytest

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.cooperative import DistanceMap, ReservationTable, plan_cooperative, plan_windowed
from warehouse_mapf.grid import Grid
from warehouse_mapf.orders import generate_orders
from warehouse_mapf.sim import Simulation
from warehouse_mapf.warehouse import generate_warehouse

CORRIDOR = Grid.from_text("""
.....
""")


def test_plan_without_reservations_is_shortest():
    path = plan_cooperative(CORRIDOR, ReservationTable(), 0, (0, 0), 0, (4, 0), stay_at_goal=False)
    assert path == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]


def test_waits_for_reserved_cell():
    table = ReservationTable()
    # robot 1, t=2 anında (2,0)'da olacak
    table.reserve_path(1, [(2, 0)], 2, park_at_end=False)
    path = plan_cooperative(CORRIDOR, table, 0, (0, 0), 0, (4, 0), stay_at_goal=False)
    assert path[2] != (2, 0)                  # o anda orada olmamalı
    assert path[-1] == (4, 0)
    assert len(path) == 6                     # bir adım bekleyerek


def test_no_head_on_swap():
    table = ReservationTable()
    # robot 1, t=0'dan t=1'e (2,0)'dan (1,0)'a geçiyor
    table.reserve_path(1, [(2, 0), (1, 0)], 0, park_at_end=False)
    path = plan_cooperative(CORRIDOR, table, 0, (1, 0), 0, (3, 0), stay_at_goal=False)
    assert path[1] != (2, 0)                  # yer değiştirme olmamalı


def test_parked_robot_blocks_forever():
    table = ReservationTable()
    table.hold(1, (2, 0), 0)
    assert plan_cooperative(CORRIDOR, table, 0, (0, 0), 0, (4, 0), stay_at_goal=False) is None


def test_release_frees_cells():
    table = ReservationTable()
    table.hold(1, (2, 0), 0)
    table.release(1)
    assert plan_cooperative(CORRIDOR, table, 0, (0, 0), 0, (4, 0), stay_at_goal=False) is not None


def test_cannot_park_on_someones_future_path():
    table = ReservationTable()
    table.reserve_path(1, [(4, 0)], 10, park_at_end=False)    # robot 1, t=10'da (4,0)'dan geçecek
    path = plan_cooperative(CORRIDOR, table, 0, (0, 0), 0, (4, 0), stay_at_goal=True)
    assert path is None or len(path) - 1 > 10


def test_windowed_plan_has_window_length_and_heads_to_goal():
    path = plan_windowed(CORRIDOR, ReservationTable(), 0, (0, 0), 0, (4, 0), 6, DistanceMap(CORRIDOR))
    assert len(path) == 7
    assert path[:5] == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
    assert path[5:] == [(4, 0), (4, 0)]          # hedefe vardıktan sonra orada bekler


def test_windowed_robot_at_goal_steps_aside():
    grid = Grid.from_text("""
        ...
        .#.
    """)
    table = ReservationTable()
    # robot 1 (0,0)'dan (2,0)'a geçecek, yolu robot 0'ın durduğu (1,0)'dan geçiyor
    table.reserve_path(1, [(0, 0), (1, 0), (2, 0)], 0, park_at_end=False)
    path = plan_windowed(grid, table, 0, (1, 0), 0, (1, 0), 4, DistanceMap(grid))
    assert path is not None
    assert path[1] != (1, 0)                     # hedefinde olsa bile kenara çekilip yol verir
    assert path[-1] == (1, 0)                    # sonra hedefine döner


@pytest.mark.parametrize("planner", ["cooperative", "windowed"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_simulation_invariants(planner, seed):
    w = generate_warehouse()
    orders = generate_orders(w, 0.45, 400, random.Random(seed))
    sim = Simulation(w, orders, 30, greedy_assign, horizon=400, planner=planner, seed=seed)
    for _ in range(400):
        before = [r.pos for r in sim.robots]
        sim.step()
        after = [r.pos for r in sim.robots]
        assert len(set(after)) == len(after)                      # aynı hücrede iki robot yok
        for i, (a, b) in enumerate(zip(before, after)):
            assert abs(a[0] - b[0]) + abs(a[1] - b[1]) <= 1         # sadece komşuya gider ya da bekler
            assert w.grid.is_free(b)
            for j in range(i + 1, len(after)):
                assert not (after[i] == before[j] and after[j] == before[i] and before[i] != before[j])
