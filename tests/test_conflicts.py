"""Çakışma tespiti testleri."""

from warehouse_mapf.conflicts import Conflict, detect_conflicts


def check(current, intended, expected):
    assert set(detect_conflicts(current, intended)) == set(expected)


def test_no_robots():
    check({}, {}, [])


def test_single_robot():
    check({0: (0, 0)}, {0: (1, 0)}, [])


def test_vertex_both_moving():
    check({0: (0, 0), 1: (2, 0)}, {0: (1, 0), 1: (1, 0)}, [Conflict("vertex", (0, 1))])


def test_vertex_into_waiting_robot():
    # 1 yerinde bekliyor, 0 onun hücresine girmek istiyor
    check({0: (0, 0), 1: (1, 0)}, {0: (1, 0), 1: (1, 0)}, [Conflict("vertex", (0, 1))])


def test_edge_swap():
    check({0: (0, 0), 1: (1, 0)}, {0: (1, 0), 1: (0, 0)}, [Conflict("edge", (0, 1))])


def test_following_is_not_a_conflict():
    check({0: (0, 0), 1: (1, 0)}, {0: (1, 0), 1: (2, 0)}, [])


def test_robot_ids_sorted_in_conflict():
    check({5: (2, 0), 3: (0, 0)}, {5: (1, 0), 3: (1, 0)}, [Conflict("vertex", (3, 5))])


def test_three_robots_same_cell():
    current = {0: (0, 1), 1: (1, 0), 2: (2, 1)}
    intended = {0: (1, 1), 1: (1, 1), 2: (1, 1)}
    check(current, intended, [
        Conflict("vertex", (0, 1)),
        Conflict("vertex", (0, 2)),
        Conflict("vertex", (1, 2)),
    ])


def test_mixed_conflicts():
    # 0-1 yer değiştiriyor, 2-3 aynı hücreye giriyor, 4 kimseyle çakışmıyor
    current = {0: (0, 0), 1: (1, 0), 2: (5, 5), 3: (7, 5), 4: (9, 9)}
    intended = {0: (1, 0), 1: (0, 0), 2: (6, 5), 3: (6, 5), 4: (9, 8)}
    check(current, intended, [Conflict("edge", (0, 1)), Conflict("vertex", (2, 3))])


def test_all_waiting():
    current = {0: (0, 0), 1: (1, 0)}
    check(current, dict(current), [])
