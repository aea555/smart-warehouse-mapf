"""Tek ajanlı A* planlayıcısının testleri."""

import pytest

from warehouse_mapf.astar import find_path, manhattan, reconstruct_path
from warehouse_mapf.grid import Cell, Grid

# manhattan


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ((0, 0), (0, 0), 0),
        ((3, 1), (5, 4), 5),
        ((5, 4), (3, 1), 5),  # simetrik olmalı
        ((0, 0), (0, 7), 7),
        ((2, 2), (5, 2), 3),
        ((-1, -1), (1, 1), 4),  # negatif koordinatlar
    ],
)
def test_manhattan(a, b, expected):
    assert manhattan(a, b) == expected


# reconstruct_path


def test_reconstruct_straight_line():
    came_from = {(1, 0): (0, 0), (2, 0): (1, 0)}
    assert reconstruct_path(came_from, (2, 0)) == [(0, 0), (1, 0), (2, 0)]


def test_reconstruct_with_turn():
    came_from = {(0, 1): (0, 0), (1, 1): (0, 1), (1, 2): (1, 1)}
    assert reconstruct_path(came_from, (1, 2)) == [(0, 0), (0, 1), (1, 1), (1, 2)]


def test_reconstruct_single_cell():
    # hedef zaten başlangıçsa tabloda hiç kayıt yoktur
    assert reconstruct_path({}, (4, 4)) == [(4, 4)]


# find_path


def test_straight_line_on_empty_grid():
    grid = Grid(5, 1)
    assert find_path(grid, (0, 0), (4, 0)) == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]


def test_start_equals_goal():
    assert find_path(Grid(5, 5), (2, 2), (2, 2)) == [(2, 2)]


def test_detours_around_wall():
    grid = Grid.from_text(
        """
        .....
        ###.#
        .....
        """
    )
    path = find_path(grid, (0, 0), (0, 2))
    assert path is not None
    assert path[0] == (0, 0) and path[-1] == (0, 2)
    assert (3, 1) in path, "duvardaki tek geçitten geçilmeli"


def test_returns_none_when_unreachable():
    grid = Grid.from_text(
        """
        ..#..
        ..#..
        ..#..
        """
    )
    assert find_path(grid, (0, 0), (4, 0)) is None


def test_returns_none_when_goal_is_blocked():
    grid = Grid.from_text(
        """
        ...
        .#.
        ...
        """
    )
    assert find_path(grid, (0, 0), (1, 1)) is None


# yolun geçerliliği


def _is_valid_path(grid: Grid, path: list[Cell] | None, start: Cell, goal: Cell) -> bool:
    if not path or path[0] != start or path[-1] != goal:
        return False
    if any(not grid.is_free(cell) for cell in path):
        return False
    return all(nxt in grid.neighbors(cur) for cur, nxt in zip(path, path[1:]))


def test_path_is_step_by_step_valid():
    grid = Grid.from_text(
        """
        ..........
        .####.###.
        .#...#...#
        .#.#.....#
        ...#.###..
        """
    )
    start, goal = (0, 0), (9, 4)
    path = find_path(grid, start, goal)
    assert path is not None
    assert _is_valid_path(grid, path, start, goal)


def test_path_is_optimal_on_empty_grid():
    # 7x5 boş ızgarada (0,0)'dan (6,4)'e gitmek için 6 + 4 + 1 = 11 hücre gerekir
    path = find_path(Grid(7, 5), (0, 0), (6, 4))
    assert path is not None
    assert len(path) == 11, f"11 hücre bekleniyordu, {len(path)} bulundu"


def test_path_is_optimal_with_obstacle():
    grid = Grid.from_text(
        """
        .....
        .###.
        .....
        """
    )
    path = find_path(grid, (0, 0), (4, 0))
    assert path is not None
    assert len(path) == 5, "üst satır boyunca giden doğrudan yol en kısası"
