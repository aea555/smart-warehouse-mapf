"""greedy_assign testleri."""

from warehouse_mapf.assignment import greedy_assign
from warehouse_mapf.orders import Order

DROP = (99, 99)


def order(id, pick, arrival=0):
    return Order(id=id, arrival=arrival, pick=pick, drop=DROP)


def test_no_orders():
    assert greedy_assign({0: (0, 0)}, []) == {}


def test_no_robots():
    assert greedy_assign({}, [order(0, (1, 1))]) == {}


def test_single():
    assert greedy_assign({4: (0, 0)}, [order(7, (3, 3))]) == {7: 4}


def test_nearest_robot_wins():
    available = {0: (0, 0), 1: (9, 0)}
    assert greedy_assign(available, [order(7, (8, 0))]) == {7: 1}


def test_example_from_docstring():
    available = {0: (0, 0), 1: (9, 0)}
    orders = [order(7, (8, 0), 0), order(8, (1, 0), 1)]
    assert greedy_assign(available, orders) == {7: 1, 8: 0}


def test_earlier_order_chooses_first():
    # İki sipariş de 1 numaralı robota daha yakın. Önce gelen (5) onu alır.
    available = {0: (0, 0), 1: (5, 0)}
    orders = [order(5, (6, 0), 0), order(6, (5, 1), 1)]
    assert greedy_assign(available, orders) == {5: 1, 6: 0}


def test_tie_goes_to_smaller_id():
    available = {3: (0, 0), 1: (4, 0)}
    assert greedy_assign(available, [order(0, (2, 0))]) == {0: 1}


def test_more_orders_than_robots():
    available = {0: (0, 0)}
    orders = [order(0, (5, 0)), order(1, (1, 0))]
    assert greedy_assign(available, orders) == {0: 0}


def test_each_robot_at_most_once():
    available = {0: (0, 0), 1: (10, 10), 2: (20, 20)}
    orders = [order(i, (0, i)) for i in range(3)]
    result = greedy_assign(available, orders)
    assert sorted(result) == [0, 1, 2]
    assert sorted(result.values()) == [0, 1, 2]
