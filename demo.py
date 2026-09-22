"""Planlayıcının bulduğu yolu metin olarak çizer.

    uv run python demo.py
"""

from warehouse_mapf.astar import find_path
from warehouse_mapf.grid import Grid

MAP = """
..........
.####.###.
.#...#...#
.#.#.....#
...#.###..
"""

grid = Grid.from_text(MAP)
start, goal = (0, 0), (9, 4)

print(f"{grid}   {start} -> {goal}\n")

try:
    path = find_path(grid, start, goal)
except NotImplementedError:
    print("find_path henüz yazılmadı.\n")
    print(grid.to_text(start=start, goal=goal))
else:
    if path is None:
        print("Yol bulunamadı.\n")
        print(grid.to_text(start=start, goal=goal))
    else:
        print(f"Yol uzunluğu: {len(path)} hücre\n")
        print(grid.to_text(path=path, start=start, goal=goal))
