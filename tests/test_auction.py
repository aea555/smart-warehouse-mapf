"""Açık artırma, blokaj ve arıza testleri."""

import random

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.astar import manhattan
from warehouse_mapf.auction import Bidder, auction
from warehouse_mapf.orders import Order, generate_orders
from warehouse_mapf.sim import Event, Simulation
from warehouse_mapf.warehouse import generate_warehouse

DROP = (50, 0)


def order(id, pick, arrival=0):
    return Order(id=id, arrival=arrival, pick=pick, drop=DROP)


def test_nearest_free_robot_wins():
    bidders = [Bidder(0, 0, (0, 0), 2), Bidder(1, 0, (10, 0), 2)]
    assert auction(bidders, [order(7, (9, 0))], manhattan) == [(7, 1)]


def test_busy_robot_finishing_soon_beats_far_free_robot():
    # robot 1 meşgul ama 2 adım sonra siparişin hemen yanında boşalacak
    bidders = [Bidder(0, 0, (0, 0), 2), Bidder(1, 2, (20, 0), 1)]
    assert auction(bidders, [order(7, (21, 0))], manhattan) == [(7, 1)]


def test_robot_takes_at_most_its_slots():
    bidders = [Bidder(0, 0, (0, 0), 1)]
    assert auction(bidders, [order(1, (1, 0)), order(2, (2, 0))], manhattan) == [(1, 0)]


def test_free_robot_can_take_a_second_order():
    bidders = [Bidder(0, 0, (0, 0), 2)]
    result = auction(bidders, [order(1, (1, 0)), order(2, (2, 0))], manhattan)
    assert sorted(result) == [(1, 0), (2, 0)]


def test_no_bidders_or_orders():
    assert auction([], [order(1, (1, 0))], manhattan) == []
    assert auction([Bidder(0, 0, (0, 0), 2)], [], manhattan) == []


def test_auction_simulation_completes_orders():
    w = generate_warehouse()
    orders = generate_orders(w, 0.3, 600, random.Random(0))
    m = Simulation(w, orders, 20, greedy_assign, horizon=400, warmup=200, planner="windowed",
                   allocation="auction").run()
    assert m.orders_completed > 0.9 * m.orders_arrived


def test_blocked_cells_are_never_entered():
    w = generate_warehouse()
    block = tuple((x, 10) for x in range(14, 26))
    orders = generate_orders(w, 0.45, 400, random.Random(1))
    for planner in ("independent", "windowed"):
        sim = Simulation(w, orders, 30, greedy_assign, horizon=400, planner=planner,
                         events=(Event("block", 100, 200, cells=block),))
        for t in range(400):
            before = {r.id: r.pos for r in sim.robots}
            sim.step()
            if 100 <= t < 300:
                for r in sim.robots:
                    assert r.pos not in block or r.pos == before[r.id]


def test_failed_robots_do_not_move_and_lose_unpicked_orders_in_auction():
    w = generate_warehouse()
    orders = generate_orders(w, 0.45, 400, random.Random(2))
    sim = Simulation(w, orders, 30, greedy_assign, horizon=400, planner="windowed",
                     allocation="auction", events=(Event("fail", 100, 50, count=5),))
    for _ in range(101):
        sim.step()
    failed = [r for r in sim.robots if r.failed(sim.t)]
    assert len(failed) == 5
    for r in failed:
        assert r.next_order is None
        assert r.phase != "to_pick" or r.order is None
    positions = {r.id: r.pos for r in failed}
    for _ in range(40):
        sim.step()
    assert all(sim.robots[i].pos == p for i, p in positions.items())
