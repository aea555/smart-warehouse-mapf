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
    return (abs(a[0] - b[0]) + abs(a[1] - b[1]));
    
def reconstruct_path(came_from: dict[Cell, Cell], goal: Cell) -> list[Cell]:
    """
    "came_from" sözlüğünü aslında bir soy ağacı gibi ele alabiliriz. eğer hedef hücreden
    başlayıp, "bu hücrenin atası kim" diye sorup oraya gidersek 
    ve ta ki atası olmayan hücre bulana
    kadar bunu yapmaya devam edersek kolaylıkla gidilmesi gereken yolu çıkarabiliriz.

    sözlükte anahtarımız şu an bulunduğumuz hücre, bu anahtarın değeri ise hücrenin atası.
    fonksiyonun sonunda listeyi dönerken ters çeviririz zira sondan başa doğru gittik.
    """
    current_cell: Cell = goal;
    cell_list = [];
    while current_cell is not None:
        cell_list.append(current_cell);
        current_cell = came_from.get(current_cell);

    cell_list.reverse();
    return cell_list;



def find_path(grid: Grid, start: Cell, goal: Cell) -> list[Cell] | None:
   
    raise NotImplementedError("TODO")
