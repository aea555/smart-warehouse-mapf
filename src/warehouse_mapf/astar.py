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

"""
    'A*' adlı algoritmayı kullanıyoruz. 
    Her hücre için bir "x mesafesi" hesaplıyoruz:
    x mesafesi = o hücreye kadar atılan adım + hücreden hedefe manhattan uzaklığı

    Oluşturmamız gerekenler:
    1) Henüz uğranmamış hücreler ve x mesafeleri.
       > "Henüz uğranmamış" olan hücrelerden kasıt uğranabilecek komşu hücreler, yani
          daha önce seçilmiş bir hücrelerin komşuları. 
    2) Her hücreye en az kaç adımda ulaşılıyor
    3) Her hücreye hangi hücreden gelindiği bilgisi 'came_from'

    Başlangıcın adım sayısı 0, x mesafesi hedef ile arasındaki manhattan kadar
    came_from boş.

    Yapmamız gereken henüz uğranmamış hücre kalmayana dek:
    - Uğranmamış hücrelerin arasından x mesafesi en az olanı seç
        * Eğer x mesafeleri aynıysa kolaylık olması açısından kuş uçuşu uzaklığı
          daha az olanı seçebiliriz
    - Seçilen hücre eğer hedefse came_from listesini reconstruct_path'e ver, en ideal
      yolu hesaplasın.
    - Seçilen hücre hedef değilse:
        * Geldiğin hücrenin adım sayısına +1 ekleyerek yeni bir adım sayısı türet.
        * Bu adım sayısını komşularla karşılaştır. Komşunun adım sayısı daha yoksa 
        ya da yeni atacağın adım sayısı kayıtlı olandan ufaksa:
            * Komşunun adım sayısını türetilen adım sayısıyla güncelle
            * came_from listesine bu hücreden bu hücreye geldim diye kayıt gir
            * hücreyi x mesafesiyle beraber listeye ekle
        * Değilse hücreyi atla
"""
def find_path(grid: Grid, start: Cell, goal: Cell) -> list[Cell] | None:
    dist = manhattan(start, goal);
    pending_list = [(dist, dist, start)];
    step_records: dict[Cell, int] = {start: 0};
    came_from: dict[Cell, Cell] = {};

    while pending_list:
        _, _, current_cell = heapq.heappop(pending_list);

        if (current_cell == goal):
            return reconstruct_path(came_from, goal);
    
        for n in grid.neighbors(current_cell):
            steps_new = step_records[current_cell] + 1;

            if (n not in step_records or steps_new < step_records[n]):
                step_records[n] = steps_new;
                came_from[n] = current_cell;
                heapq.heappush(pending_list, (step_records[n] + manhattan(n, goal), manhattan(n, goal), n));
    
    return None;

        



    

