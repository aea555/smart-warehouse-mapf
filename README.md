# Multi-Agent Smart Warehouse Simulator

BLM5026 Bilgisayar Oyunlarında Yapay Zeka dersi dönem projesi.

Bir depoda çok sayıda robot raflardan ürün alıp paketleme masalarına taşıyor. Robot sayısı arttıkça
robotlar dar koridorlarda karşılaşıyor, birbirini bekliyor ve bazen hiçbiri ilerleyemiyor. Bu projede
robotların birbirini kilitlemeden çalışabilmesi için farklı yöntemler denenecek.

Simülasyon için Python, görselleştirme için Unity kullanılıyor.

## Kurulum

Kurulum için: [uv](https://docs.astral.sh/uv/)

```bash
uv sync         # bağımlılıkları kurar
uv run pytest   # testleri çalıştırır
```

## Demo

```bash
uv run python demo.py   # küçük bir haritada A* ile bulunan yolu ekrana çizer
```

## Yöntem

Şimdilik sadece baseline var. Sipariş en yakın boştaki robota verilir ve her robot yolunu A* ile bulur.
Robotlar diğer robotları hesaba katmaz. Bir robot önündeki robot yüzünden birkaç adım ilerleyemezse
yolunu yeniden planlar (Local Repair A*).

## Deney

```bash
uv run python tools/run_experiments.py   # farklı yük ve raf yoğunluklarında baseline'ı çalıştırır
```

Sonuçlar `results/experiments.csv` dosyasına yazılır. Aynı seed her çalıştırmada aynı siparişleri üretir.

## Unity

Unity 6 ve URP kullanılıyor, proje `unity/` klasöründe. Unity simülasyonu kendisi çalıştırmaz,
Python'un kaydettiği simülasyonları oynatır.

```bash
uv run python tools/export_replay.py   # simülasyon kayıtlarını unity/Assets/StreamingAssets/replay.json dosyasına yazar
```

Sonra `unity/` klasörü Unity Hub ile açılır ve `Assets/Scenes/Replay.unity` sahnesi çalıştırılır.

![Baseline](docs/media/baseline-orta.png)

Tek robotun A* yolunu gösteren ilk sahne de duruyor. O sahne için `tools/export_scene.py` çalıştırılıp
`Assets/Scenes/Warehouse.unity` açılır.

## Plan

1. Izgara modeli ve tek robot için A*
2. Birden fazla robot ve basit görev atama (baseline)
3. Robotların birbirinin yolunu bildiği planlama (Cooperative A*)
4. Açık artırma ile görev atama
5. Unity ile görselleştirme
6. Deneyler ve makale
