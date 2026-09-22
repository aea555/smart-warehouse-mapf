"""Tek robot için A* ile en kısa yol."""

from __future__ import annotations

import heapq

from .grid import Cell, Grid


def manhattan(a: Cell, b: Cell) -> int:
    """
    sadece sağ-sol ve yukarı-aşağı yapabildiğimiz için, aslında asıl mesafe 
    pisagor ile değil koordinatların mutlak değerlerinin farkı olarak
    hesaplanmalı.

    burada hiç bir şey hesaba katılmıyor, sadece koordinatlar arasında çapraz
    gidiş olmadan mesafe nedir o hesaplanıyor.
    """
    raise NotImplementedError("TODO")


def reconstruct_path(came_from: dict[Cell, Cell], goal: Cell) -> list[Cell]:
    """
    "came_from" sözlüğünü aslında bir soy ağacı gibi ele alabiliriz. eğer hedef hücreden
    başlayıp, "bu hücrenin atası kim" diye sorup oraya gidersek 
    ve ta ki atası olmayan hücre bulana
    kadar bunu yapmaya devam edersek kolaylıkla gidilmesi gereken yolu çıkarabiliriz.

    sözlükte anahtarımız şu an bulunduğumuz hücre, bu anahtarın değeri ise hücrenin atası.
    fonksiyonun sonunda listeyi dönerken ters çeviririz zira sondan başa doğru gittik.
    """
    raise NotImplementedError("TODO")


def find_path(grid: Grid, start: Cell, goal: Cell) -> list[Cell] | None:
    raise NotImplementedError("TODO")
