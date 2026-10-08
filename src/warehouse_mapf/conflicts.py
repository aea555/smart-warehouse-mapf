"""Robotlar arası çakışmaları bulur.

İki tür çakışma var: iki robot aynı hücreye girmek isterse vertex, iki robot yer
değiştirmek isterse edge çakışması.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grid import Cell


@dataclass(frozen=True)
class Conflict:
    kind: str                 # "vertex" ya da "edge"
    robots: tuple[int, int]   # çakışan iki robotun id'si, küçük olan önce


def detect_conflicts(current: dict[int, Cell], intended: dict[int, Cell]) -> list[Conflict]:
    """Bir sonraki adımda oluşacak çakışmaları bulur.

    current: robot id -> şu anki hücre
    intended: robot id -> sonraki adımda olmak istediği hücre (bekleyen için kendi hücresi)

    vertex çakışmasında iki robot aynı hücreye girer, edge çakışmasında iki robot yer değiştirir.
    Boşalan hücreye arkadan girmek çakışma sayılmaz. Her çakışan çift için bir kayıt döner.
    """
    # TODO
    raise NotImplementedError
