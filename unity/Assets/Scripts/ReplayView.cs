using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;

// replays/ klasöründeki kayıtları oynatır ve politikaları karşılaştırır.
//
// Robotların hareketi Python simülasyonundan gelir (src/warehouse_mapf/sim.py). Unity sadece çizer.
//
// Her senaryo dört politikayla ayrı ayrı kaydedildi, hepsi aynı siparişleri görür. Politika
// değişince aynı adım gösterilir. Sağ paneldeki tablo ve grafik dört politikayı yan yana verir.
//
// Haritada dolu/boş daire ürün taşıyıp taşımadığını, kırmızı ilerleyemediğini gösterir. Arızalı
// robot gri ve çarpılı. Isı haritası son 100 adımda robotların görevdeyken beklediği hücreleri boyar.
//
// Kontroller: boşluk oynat/duraklat, sağ/sol ok tek adım, tekerlek yakınlaştır, sürükle kaydır,
// robota tıkla rotasını gör, 1-4 politika, Esc seçimi kaldır.
//
// Python'da y aşağı doğru artar, Unity'de yukarı. Bu yüzden y eksi ile çevrilir.
public class ReplayView : MonoBehaviour
{
    [SerializeField] private string replayFolder = "replays";

    // renkler
    private static readonly Color Background = new Color(0.07f, 0.08f, 0.10f);
    private static readonly Color Floor      = new Color(0.17f, 0.19f, 0.23f);
    private static readonly Color Wall       = new Color(0.11f, 0.12f, 0.15f);
    private static readonly Color Shelf      = new Color(0.72f, 0.47f, 0.22f);
    private static readonly Color Station    = new Color(0.20f, 0.65f, 0.60f);
    private static readonly Color DropMark   = new Color(0.17f, 0.36f, 0.37f);
    private static readonly Color ParkMark   = new Color(0.24f, 0.27f, 0.32f);
    private static readonly Color OrderColor = new Color(0.98f, 0.80f, 0.25f);
    private static readonly Color Moving     = new Color(0.36f, 0.66f, 1.00f);
    private static readonly Color Stuck      = new Color(1.00f, 0.30f, 0.30f);
    private static readonly Color Failed     = new Color(0.55f, 0.57f, 0.60f);
    private static readonly Color Closed     = new Color(0.85f, 0.18f, 0.22f, 0.9f);
    private static readonly Color Selected   = Color.white;
    private static readonly Color Muted      = new Color(0.60f, 0.64f, 0.68f);

    // politika renkleri, makaledeki grafiklerle aynı sırada
    private static readonly Color[] PolicyColors =
    {
        new Color(0.82f, 0.29f, 0.36f), new Color(0.24f, 0.60f, 0.80f),
        new Color(0.93f, 0.68f, 0.29f), new Color(0.66f, 0.55f, 0.98f),
    };

    private static readonly string[] PhaseNames = { "boşta", "toplamaya gidiyor", "ürünle teslimata gidiyor", "parka dönüyor" };

    // ekran düzeni, 720 piksel yüksekliğe göre
    private const float RefHeight = 720f;
    private const float TopBar = 104f;
    private const float BottomBar = 66f;
    private const float SideW = 340f;

    private const float MinSpeed = 0.25f, MaxSpeed = 30f;
    private const float DimAlpha = 0.22f;
    private const int MapPx = 8;            // harita dokusunda hücre başına piksel
    private const int HeatWindow = 100;     // ısı haritası son kaç adıma bakar
    private const float HeatCap = 40f;      // bu kadar bekleme tam kırmızı

    private ReplayIndex index;
    private int scenario, policy;
    private ScenarioInfo Info => index.scenarios[scenario];
    private readonly Dictionary<string, ReplayRun> cache = new Dictionary<string, ReplayRun>();
    private ReplayRun run;

    private Transform world;
    private Sprite square, circle, hollow, ring, arrow, cross;
    private Material spriteMaterial;

    private SpriteRenderer[] robots = new SpriteRenderer[0];
    private SpriteRenderer[] arrows = new SpriteRenderer[0];
    private SpriteRenderer[] crosses = new SpriteRenderer[0];
    private readonly List<SpriteRenderer> orderPool = new List<SpriteRenderer>();
    private readonly List<SpriteRenderer> closedPool = new List<SpriteRenderer>();
    private Transform orderRoot, closedRoot;

    // ısı haritası
    private Texture2D heatTex;
    private SpriteRenderer heatSprite;
    private Color32[] heatPixels;
    private int[] heatCounts;
    private int heatFrame = -1;

    // seçili robot
    private int selected = -1;
    private LineRenderer routeLine;
    private SpriteRenderer selectRing, targetMark;

    // katmanlar
    private bool showArrows;
    private bool showOrders = true;
    private bool showHeat;

    private float time;                 // kayıttaki yer, kesirli adım
    private bool playing;
    private float stepsPerSecond = 2f;
    private string loadError;

    private Camera cam;
    private float fitSize;
    private bool dragging;
    private Vector2 pressPos, lastMouse;

    private Texture2D chartTex;
    private GUIStyle panelStyle, titleStyle, textStyle, smallStyle, statStyle, buttonStyle, cardStyle, cellStyle, rowStyle;
    private Texture2D rowSelectedTex, warmupTex, eventTex, cursorTex, trackTex;

    // kurulum

    private void Start()
    {
        square = SpriteUtil.Square();
        circle = SpriteUtil.Circle();
        hollow = SpriteUtil.Ring(64, 0.38f);
        ring = SpriteUtil.Ring();
        arrow = SpriteUtil.Arrow();
        cross = SpriteUtil.Cross();
        spriteMaterial = SpriteUtil.UnlitMaterial();
        cam = Camera.main;

        string file = Path.Combine(Application.streamingAssetsPath, replayFolder, "index.json");
        if (!File.Exists(file))
        {
            loadError = "replays/index.json bulunamadi. Once: uv run python tools/export_replay.py";
            return;
        }
        index = JsonUtility.FromJson<ReplayIndex>(File.ReadAllText(file));
        if (index.scenarios == null || index.scenarios.Length == 0)
        {
            loadError = "index.json icinde senaryo yok.";
            return;
        }
        policy = index.policies.Length - 1;      // en gelişmiş politikayla başla
        ShowScenario(0);
    }

    private ReplayRun Load(int s, int p)
    {
        string key = $"{index.scenarios[s].id}_{index.policies[p].id}";
        if (cache.TryGetValue(key, out var cached)) return cached;
        string file = Path.Combine(Application.streamingAssetsPath, replayFolder, key + ".json");
        var r = JsonUtility.FromJson<ReplayRun>(File.ReadAllText(file));
        cache[key] = r;
        return r;
    }

    private void ShowScenario(int s)
    {
        scenario = (s + index.scenarios.Length) % index.scenarios.Length;
        cache.Clear();                       // sadece açık senaryonun kayıtları bellekte kalsın
        time = 0f;
        playing = false;
        selected = -1;
        ShowPolicy(policy, fit: true);
        BuildChart();
    }

    private void ShowPolicy(int p, bool fit = false)
    {
        policy = (p + index.policies.Length) % index.policies.Length;
        run = Load(scenario, policy);
        if (world != null) Destroy(world.gameObject);
        world = new GameObject("World").transform;
        if (selected >= run.robots) selected = -1;
        Build();
        if (fit) FitCamera();
        heatFrame = -1;
        Apply();
    }

    private static Vector3 World(float x, float y) => new Vector3(x, -y, 0f);

    private void Build()
    {
        BuildMap();

        closedRoot = new GameObject("Closed").transform;
        closedRoot.SetParent(world, false);
        closedPool.Clear();
        orderRoot = new GameObject("Orders").transform;
        orderRoot.SetParent(world, false);
        orderPool.Clear();

        var robotRoot = new GameObject("Robots").transform;
        robotRoot.SetParent(world, false);
        int n = run.robots;
        robots = new SpriteRenderer[n];
        arrows = new SpriteRenderer[n];
        crosses = new SpriteRenderer[n];
        for (int i = 0; i < n; i++)
        {
            robots[i] = Spawn($"Robot {i}", circle, Vector3.zero, Moving, 0.72f, 5, robotRoot);
            arrows[i] = Child(robots[i], arrow, Color.white, 0.45f, 7);
            crosses[i] = Child(robots[i], cross, new Color(0.12f, 0.12f, 0.14f), 0.8f, 6);
        }

        // seçim göstergeleri
        var lineGo = new GameObject("Route");
        lineGo.transform.SetParent(world, false);
        routeLine = lineGo.AddComponent<LineRenderer>();
        routeLine.sharedMaterial = spriteMaterial;
        routeLine.startWidth = routeLine.endWidth = 0.14f;
        routeLine.startColor = routeLine.endColor = Selected;
        routeLine.sortingOrder = 4;
        routeLine.numCornerVertices = 2;
        routeLine.positionCount = 0;

        selectRing = Spawn("SelectRing", ring, Vector3.zero, Selected, 1.25f, 8, world);
        targetMark = Spawn("Target", ring, Vector3.zero, Selected, 0.9f, 8, world);
        selectRing.enabled = targetMark.enabled = false;
    }

    // Sabit harita tek bir doku olarak çizilir. Büyük depoda binlerce nesne yerine tek sprite yeterli.
    // Hücreler arasında bir piksel boşluk kalır, ızgara okunsun diye.
    private void BuildMap()
    {
        int w = run.width, h = run.height;
        var colors = new Color32[w * h];
        for (int i = 0; i < colors.Length; i++) colors[i] = Floor;
        void Paint(CellXY[] cells, Color c) { foreach (var q in cells) colors[q.x + q.y * w] = c; }
        Paint(run.parks, ParkMark);
        Paint(run.drops, DropMark);
        Paint(run.shelves, Shelf);
        Paint(run.walls ?? new CellXY[0], Wall);
        Paint(run.stations, Station);

        var tex = SpriteUtil.CellTexture(w * MapPx, h * MapPx);
        var px = new Color32[w * MapPx * h * MapPx];
        Color32 gap = Background;
        for (int py = 0; py < h * MapPx; py++)
        for (int pxX = 0; pxX < w * MapPx; pxX++)
        {
            int cx = pxX / MapPx, cy = h - 1 - py / MapPx;        // doku alttan başlar
            bool edge = pxX % MapPx == 0 || py % MapPx == 0;
            Color32 c = colors[cx + cy * w];
            bool solid = c.Equals((Color32)Shelf) || c.Equals((Color32)Wall);   // raflar bitişik görünsün
            px[pxX + py * w * MapPx] = edge && !solid ? gap : c;
        }
        tex.SetPixels32(px);
        tex.Apply();
        var map = Spawn("Map", Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f), MapPx),
                        World((w - 1) / 2f, (h - 1) / 2f), Color.white, 1f, 0, world);
        map.name = "Map";

        heatTex = SpriteUtil.CellTexture(w, h);
        heatPixels = new Color32[w * h];
        heatCounts = new int[w * h];
        heatTex.SetPixels32(heatPixels);
        heatTex.Apply();
        heatSprite = Spawn("Heat", Sprite.Create(heatTex, new Rect(0, 0, w, h), new Vector2(0.5f, 0.5f), 1f),
                           World((w - 1) / 2f, (h - 1) / 2f), Color.white, 1f, 2, world);
        heatSprite.enabled = showHeat;
    }

    private SpriteRenderer Spawn(string name, Sprite sprite, Vector3 pos, Color color,
                                 float scale, int order, Transform parent)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        go.transform.position = pos;
        go.transform.localScale = new Vector3(scale, scale, 1f);
        var sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = sprite;
        sr.color = color;
        sr.sortingOrder = order;
        if (spriteMaterial != null) sr.sharedMaterial = spriteMaterial;
        return sr;
    }

    private SpriteRenderer Child(SpriteRenderer parent, Sprite sprite, Color color, float scale, int order)
    {
        var sr = Spawn("Child", sprite, Vector3.zero, color, scale, order, parent.transform);
        sr.transform.localPosition = Vector3.zero;
        sr.transform.localScale = new Vector3(scale, scale, 1f);
        return sr;
    }

    // kamera ve fare

    // kamera sadece üst/alt çubuklar ve sağ panelin arasına çizer
    private void UpdateViewport()
    {
        float k = Screen.height / RefHeight;
        float side = Mathf.Min(SideW * k / Screen.width, 0.6f);
        cam.rect = new Rect(0f, BottomBar / RefHeight, 1f - side, 1f - (TopBar + BottomBar) / RefHeight);
    }

    // haritanın tamamı harita alanına sığsın
    private void FitCamera()
    {
        cam.orthographic = true;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Background;
        UpdateViewport();

        const float margin = 1f;
        float sizeH = (run.height + margin) / 2f;
        float sizeW = (run.width + margin) / (2f * cam.aspect);
        fitSize = Mathf.Max(sizeH, sizeW);
        cam.orthographicSize = fitSize;
        cam.transform.position = new Vector3((run.width - 1) / 2f, -(run.height - 1) / 2f, -10f);
    }

    private void HandleMouse()
    {
        var mouse = Mouse.current;
        if (mouse == null) return;
        Vector2 pos = mouse.position.ReadValue();
        float k = Screen.height / RefHeight;
        bool overCanvas = cam.pixelRect.Contains(pos)
                          && !(selected >= 0 && CardRect().Contains(new Vector2(pos.x / k, (Screen.height - pos.y) / k)));

        float scroll = mouse.scroll.ReadValue().y;
        if (overCanvas && Mathf.Abs(scroll) > 0.01f)
        {
            Vector3 before = cam.ScreenToWorldPoint(pos);
            float factor = scroll > 0 ? 0.88f : 1f / 0.88f;
            cam.orthographicSize = Mathf.Clamp(cam.orthographicSize * factor, 3f, fitSize * 1.5f);
            Vector3 after = cam.ScreenToWorldPoint(pos);
            cam.transform.position += before - after;   // imlecin altındaki nokta yerinde kalsın
        }

        if (mouse.leftButton.wasPressedThisFrame && overCanvas) { dragging = true; pressPos = lastMouse = pos; }
        if (dragging && mouse.leftButton.isPressed)
        {
            Vector3 delta = cam.ScreenToWorldPoint(lastMouse) - cam.ScreenToWorldPoint(pos);
            cam.transform.position += new Vector3(delta.x, delta.y, 0f);
            lastMouse = pos;
        }
        if (dragging && mouse.leftButton.wasReleasedThisFrame)
        {
            dragging = false;
            if ((pos - pressPos).magnitude < 6f) Select(RobotAt(cam.ScreenToWorldPoint(pos)));   // sürükleme değil, tık
        }
    }

    private int RobotAt(Vector3 p)
    {
        int best = -1;
        float bestD = 0.6f;
        for (int r = 0; r < robots.Length; r++)
        {
            float d = Vector2.Distance(robots[r].transform.position, p);
            if (d < bestD) { bestD = d; best = r; }
        }
        return best;
    }

    private void Select(int r)
    {
        selected = r;
        Apply();
    }

    // oynatma

    private int LastFrame => run.frames.Length - 1;
    private int FrameIndex => Mathf.Clamp(Mathf.FloorToInt(time), 0, LastFrame);

    private void Update()
    {
        if (run == null) return;
        UpdateViewport();
        HandleMouse();

        var kb = Keyboard.current;
        if (kb != null)
        {
            if (kb.spaceKey.wasPressedThisFrame) TogglePlay();
            if (kb.rightArrowKey.wasPressedThisFrame) Seek(Mathf.Floor(time) + 1f);
            if (kb.leftArrowKey.wasPressedThisFrame) Seek(Mathf.Ceil(time) - 1f);
            if (kb.escapeKey.wasPressedThisFrame) Select(-1);
            if (kb.digit1Key.wasPressedThisFrame) ShowPolicy(0);
            if (kb.digit2Key.wasPressedThisFrame) ShowPolicy(1);
            if (kb.digit3Key.wasPressedThisFrame) ShowPolicy(2);
            if (kb.digit4Key.wasPressedThisFrame) ShowPolicy(3);
        }

        if (!playing) return;
        time += stepsPerSecond * Time.deltaTime;
        if (time >= LastFrame) { time = LastFrame; playing = false; }
        Apply();
    }

    private void TogglePlay()
    {
        if (time >= LastFrame) time = 0f;
        playing = !playing;
    }

    private void Seek(float t)
    {
        playing = false;
        time = Mathf.Clamp(t, 0f, LastFrame);
        Apply();
    }

    // robotları, siparişleri, kapalı hücreleri ve seçimi şu anki zamana göre çizer
    private void Apply()
    {
        int i = FrameIndex;
        int j = Mathf.Min(i + 1, LastFrame);
        float f = Mathf.SmoothStep(0f, 1f, time - i);   // hücreden hücreye yumuşak geçiş
        var a = run.frames[i];
        var b = run.frames[j];
        bool focus = selected >= 0;

        for (int r = 0; r < robots.Length; r++)
        {
            float x = Mathf.Lerp(a.xs[r], b.xs[r], f);
            float y = Mathf.Lerp(a.ys[r], b.ys[r], f);
            robots[r].transform.position = World(x, y);

            // dolu daire ürün taşıyor, boş daire taşımıyor, kırmızı ilerleyemiyor, gri çarpılı arızalı
            bool broken = Array.IndexOf(a.failed, r) >= 0;
            robots[r].sprite = a.phase[r] == 2 || broken ? circle : hollow;
            Color c = broken ? Failed : a.blocked[r] > 0 ? Stuck : Moving;
            if (focus && r != selected) c.a = DimAlpha;
            robots[r].color = c;
            crosses[r].enabled = broken;

            int dx = a.nx[r] - a.xs[r], dy = a.ny[r] - a.ys[r];
            bool wants = !broken && (showArrows || r == selected) && (dx != 0 || dy != 0);
            arrows[r].enabled = wants;
            if (wants)
            {
                arrows[r].transform.localPosition = new Vector3(dx, -dy, 0f) * 0.62f;
                arrows[r].transform.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(-dy, dx) * Mathf.Rad2Deg);
                Color ac = a.blocked[r] > 0 ? Stuck : Color.white;
                if (focus && r != selected) ac.a = DimAlpha;
                arrows[r].color = ac;
            }
        }

        Pool(orderPool, orderRoot, showOrders ? a.openPicks : new CellXY[0], OrderColor, 0.30f, 3, 45f,
             focus ? DimAlpha : 1f);
        Pool(closedPool, closedRoot, a.closed ?? new CellXY[0], Closed, 0.92f, 1, 0f, 1f);

        if (showHeat && heatFrame != i) UpdateHeat(i);
        heatSprite.enabled = showHeat;

        DrawSelection(a);
    }

    // bekleyen sipariş ve kapalı hücre işaretleri, havuzdan tekrar kullanılır
    private void Pool(List<SpriteRenderer> pool, Transform root, CellXY[] cells, Color color,
                      float scale, int order, float angle, float alpha)
    {
        while (pool.Count < cells.Length)
        {
            var d = Spawn("Mark", square, Vector3.zero, color, scale, order, root);
            d.transform.rotation = Quaternion.Euler(0f, 0f, angle);
            pool.Add(d);
        }
        for (int k = 0; k < pool.Count; k++)
        {
            bool on = k < cells.Length;
            pool[k].enabled = on;
            if (!on) continue;
            pool[k].transform.position = World(cells[k].x, cells[k].y);
            pool[k].color = new Color(color.r, color.g, color.b, color.a * alpha);
        }
    }

    // Son 100 adımda görevdeki bir robot yerinden kımıldamadıysa, durduğu hücreye bir puan yazılır.
    // Puan arttıkça hücre sarıdan kırmızıya döner.
    private void UpdateHeat(int i)
    {
        heatFrame = i;
        int w = run.width, h = run.height;
        Array.Clear(heatCounts, 0, heatCounts.Length);
        for (int t = Mathf.Max(1, i - HeatWindow + 1); t <= i; t++)
        {
            var prev = run.frames[t - 1];
            var fr = run.frames[t];
            for (int r = 0; r < fr.xs.Length; r++)
            {
                if (fr.phase[r] == 0 || fr.xs[r] != prev.xs[r] || fr.ys[r] != prev.ys[r]) continue;
                if (Array.IndexOf(fr.failed, r) >= 0) continue;
                heatCounts[fr.xs[r] + fr.ys[r] * w]++;
            }
        }
        var low = new Color(1f, 0.85f, 0.25f);
        var high = new Color(1f, 0.15f, 0.15f);
        for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++)
        {
            int n = heatCounts[x + y * w];
            int p = x + (h - 1 - y) * w;                 // doku alttan başlar
            if (n == 0) { heatPixels[p] = new Color32(0, 0, 0, 0); continue; }
            float v = Mathf.Clamp01(n / HeatCap);
            Color c = Color.Lerp(low, high, v);
            c.a = 0.35f + 0.55f * v;
            heatPixels[p] = c;
        }
        heatTex.SetPixels32(heatPixels);
        heatTex.Apply();
    }

    // seçili robotun rotası ve hedefi
    private void DrawSelection(ReplayFrame a)
    {
        bool on = selected >= 0;
        selectRing.enabled = targetMark.enabled = on;
        if (!on) { routeLine.positionCount = 0; return; }

        Vector3 here = robots[selected].transform.position;
        selectRing.transform.position = here;
        targetMark.transform.position = World(a.tx[selected], a.ty[selected]);

        var pts = new List<Vector3> { here };
        int p = a.plan[selected];
        if (p >= 0)
        {
            var plan = run.plans[p];
            for (int k = a.planOffset[selected]; k < plan.xs.Length; k++) pts.Add(World(plan.xs[k], plan.ys[k]));
        }
        routeLine.positionCount = pts.Count;
        routeLine.SetPositions(pts.ToArray());
    }

    // karşılaştırma grafiği

    private const int ChartW = 620, ChartH = 250;    // doku boyutu, ekranda yarısı kadar çizilir

    // Dört politikanın ısınmadan sonra biten sipariş eğrisi tek dokuya çizilir.
    // Senaryo değişince bir kez üretilir, oynarken sadece imleç çizgisi kayar.
    private void BuildChart()
    {
        var info = Info;
        int steps = info.series[0].completed.Length;
        int max = 1;
        foreach (var s in info.series) max = Mathf.Max(max, s.completed[steps - 1]);
        max = Mathf.CeilToInt(max * 1.08f);

        if (chartTex == null) chartTex = new Texture2D(ChartW, ChartH, TextureFormat.RGBA32, false);
        var px = new Color32[ChartW * ChartH];
        Color32 bg = new Color(0.10f, 0.11f, 0.14f);
        Color32 warm = new Color(0.20f, 0.18f, 0.12f);
        Color32 evt = new Color(0.25f, 0.12f, 0.14f);
        Color32 grid = new Color(0.17f, 0.19f, 0.23f);
        for (int x = 0; x < ChartW; x++)
        {
            int step = x * (steps - 1) / (ChartW - 1);
            Color32 col = step < info.warmup ? warm : bg;
            foreach (var e in info.events)
                if (step >= e.start && step < e.start + e.duration) col = evt;
            for (int y = 0; y < ChartH; y++) px[x + y * ChartW] = col;
        }
        for (int g = 1; g < 4; g++)
            for (int x = 0; x < ChartW; x++) px[x + g * ChartH / 4 * ChartW] = grid;

        for (int p = 0; p < info.series.Length; p++)
        {
            Color32 c = PolicyColors[p % PolicyColors.Length];
            var s = info.series[p].completed;
            int lastY = -1;
            for (int x = 0; x < ChartW; x++)
            {
                int step = x * (steps - 1) / (ChartW - 1);
                int y = Mathf.RoundToInt((ChartH - 4) * s[step] / (float)max) + 2;
                int y0 = lastY < 0 ? y : Mathf.Min(lastY, y), y1 = lastY < 0 ? y : Mathf.Max(lastY, y);
                for (int yy = y0 - 1; yy <= y1 + 1; yy++)
                    for (int xx = x; xx <= Mathf.Min(x + 1, ChartW - 1); xx++)
                        if (yy >= 0 && yy < ChartH) px[xx + yy * ChartW] = c;
                lastY = y;
            }
        }
        for (int i = 0; i < px.Length; i++) px[i] = ((Color)px[i]).linear;   // IMGUI için, bkz. Solid
        chartTex.SetPixels32(px);
        chartTex.Apply();
        chartMax = max;
    }

    private int chartMax;

    // arayüz

    private void InitStyles()
    {
        if (panelStyle != null) return;
        panelStyle = new GUIStyle { normal = { background = Solid(new Color(0.04f, 0.045f, 0.06f, 1f)) }, padding = new RectOffset(14, 14, 8, 8) };
        cardStyle  = new GUIStyle { normal = { background = Solid(new Color(0.06f, 0.07f, 0.09f, 0.94f)) }, padding = new RectOffset(14, 14, 10, 10) };
        titleStyle = new GUIStyle { fontSize = 17, fontStyle = FontStyle.Bold, richText = true, normal = { textColor = Color.white } };
        textStyle  = new GUIStyle { fontSize = 13, richText = true, wordWrap = true, normal = { textColor = new Color(0.78f, 0.81f, 0.86f) } };
        smallStyle = new GUIStyle(textStyle) { fontSize = 11, normal = { textColor = Muted } };
        statStyle  = new GUIStyle(textStyle) { fontSize = 14, wordWrap = false };
        buttonStyle = new GUIStyle(GUI.skin.button) { fontSize = 13, fixedHeight = 26, richText = true };
        cellStyle = new GUIStyle(textStyle) { wordWrap = false, alignment = TextAnchor.MiddleRight };
        rowStyle = new GUIStyle { padding = new RectOffset(6, 6, 3, 3), hover = { background = Solid(new Color(1f, 1f, 1f, 0.05f)) } };
        rowSelectedTex = Solid(new Color(1f, 1f, 1f, 0.09f));
        warmupTex = Solid(new Color(0.95f, 0.79f, 0.30f, 0.35f));
        eventTex = Solid(new Color(0.85f, 0.18f, 0.22f, 0.45f));
        cursorTex = Solid(new Color(1f, 1f, 1f, 0.85f));
        trackTex = Solid(new Color(0.22f, 0.24f, 0.28f));
    }

    private static Texture2D Solid(Color c)
    {
        // Proje doğrusal renk uzayında, IMGUI ise dokuyu bir kez daha çeviriyor.
        // Renk önce doğrusala çevrilir ki ekranda yazıldığı gibi görünsün.
        var t = new Texture2D(1, 1);
        var lin = c.linear;
        t.SetPixel(0, 0, new Color(lin.r, lin.g, lin.b, c.a));
        t.Apply();
        return t;
    }

    private static string Hex(Color c) => ColorUtility.ToHtmlStringRGB(c);

    // kart robotun karşı tarafında durur, robotu ve rotasını örtmesin
    private Rect CardRect()
    {
        float w = Screen.width / (Screen.height / RefHeight);
        bool robotOnRight = selected >= 0 && cam.WorldToViewportPoint(robots[selected].transform.position).x > 0.5f;
        float x = robotOnRight ? 14f : w - SideW - 300f;
        return new Rect(x, TopBar + 12, 286, 170);
    }

    private string ActiveEvent(int step)
    {
        foreach (var e in Info.events)
        {
            if (step < e.start || step >= e.start + e.duration) continue;
            int left = e.start + e.duration - step;
            return e.kind == "block" ? $"Koridor kapalı · {left} adım kaldı" : $"Robotlar arızalı · {left} adım kaldı";
        }
        return null;
    }

    private void OnGUI()
    {
        InitStyles();
        float k = Screen.height / RefHeight;
        GUI.matrix = Matrix4x4.Scale(new Vector3(k, k, 1f));
        float w = Screen.width / k;
        float h = RefHeight;

        if (loadError != null)
        {
            GUI.Label(new Rect(20, 20, 900, 40), loadError, titleStyle);
            return;
        }

        int step = FrameIndex;
        var fr = run.frames[step];

        DrawTopBar(w, step);
        DrawSidePanel(w, h, step);
        if (selected >= 0) DrawCard(fr);
        DrawBottomBar(w, h);
    }

    private void DrawTopBar(float w, int step)
    {
        GUI.Box(new Rect(0, 0, w, TopBar), GUIContent.none, panelStyle);
        const float controlsW = 430f;
        float left = w - controlsW - 28;

        GUILayout.BeginArea(new Rect(14, 8, left, TopBar - 10));
        GUILayout.BeginHorizontal();
        GUILayout.Label("Senaryo", smallStyle, GUILayout.Width(62));
        var titles = new string[index.scenarios.Length];
        for (int s = 0; s < titles.Length; s++) titles[s] = index.scenarios[s].title;
        int ns = GUILayout.Toolbar(scenario, titles, buttonStyle);
        GUILayout.EndHorizontal();
        if (ns != scenario) ShowScenario(ns);

        GUILayout.Space(4);
        GUILayout.BeginHorizontal();
        GUILayout.Label("Politika", smallStyle, GUILayout.Width(62));
        var names = new string[index.policies.Length];
        for (int p = 0; p < names.Length; p++)
            names[p] = $"<color=#{Hex(PolicyColors[p])}>●</color> {index.policies[p].id} · {index.policies[p].name}";
        int np = GUILayout.Toolbar(policy, names, buttonStyle);
        GUILayout.EndHorizontal();
        if (np != policy) ShowPolicy(np);

        GUILayout.Space(3);
        string phase = step < run.warmup ? "  <color=#f2c94c>ısınma (ölçüme dahil değil)</color>" : "";
        string evt = ActiveEvent(step);
        string evtText = evt != null ? $"   <color=#ff6b6b><b>{evt}</b></color>" : "";
        GUILayout.Label($"Adım <b>{step}</b>/{LastFrame}{phase}{evtText}   <color=#9aa3ad>{index.policies[policy].about}</color>", statStyle);
        GUILayout.EndArea();

        GUILayout.BeginArea(new Rect(w - controlsW - 14, 8, controlsW, TopBar - 12));
        GUILayout.BeginHorizontal();
        if (GUILayout.Button(playing ? "❚❚ Duraklat" : "▶ Başlat", buttonStyle, GUILayout.Width(100))) TogglePlay();
        if (GUILayout.Button("◀ Adım", buttonStyle)) Seek(Mathf.Ceil(time) - 1f);
        if (GUILayout.Button("Adım ▶", buttonStyle)) Seek(Mathf.Floor(time) + 1f);
        if (GUILayout.Button("Isınmayı atla »", buttonStyle, GUILayout.Width(118))) Seek(run.warmup);
        GUILayout.EndHorizontal();
        GUILayout.BeginHorizontal();
        if (GUILayout.Button("Başa sar", buttonStyle)) Seek(0f);
        if (GUILayout.Button("Haritayı sığdır", buttonStyle)) FitCamera();
        GUILayout.EndHorizontal();
        GUILayout.EndArea();
    }

    private void DrawSidePanel(float w, float h, int step)
    {
        var info = Info;
        var area = new Rect(w - SideW, TopBar, SideW, h - TopBar - BottomBar);
        GUI.Box(area, GUIContent.none, panelStyle);
        GUILayout.BeginArea(new Rect(area.x + 14, area.y + 10, area.width - 28, area.height - 16));

        GUILayout.Label(info.title, titleStyle);
        GUILayout.Label($"{info.about}  <color=#9aa3ad>({info.rate:0.##} sipariş/adım, seed {info.seed})</color>", textStyle);
        GUILayout.Space(8);

        // dört politikanın tablosu
        GUILayout.Label("Aynı sipariş akışında, bu adımda:", smallStyle);
        float measured = step - info.warmup;
        GUILayout.BeginHorizontal();
        GUILayout.Label("", smallStyle, GUILayout.Width(36));
        Header("Tamam.", 52); Header("100 adımda", 74); Header("Ort. süre", 62); Header("Sıkışan", 56);
        GUILayout.EndHorizontal();
        for (int p = 0; p < info.series.Length; p++)
        {
            var s = info.series[p];
            var style = new GUIStyle(rowStyle);
            if (p == policy) style.normal.background = rowSelectedTex;
            GUILayout.BeginHorizontal(style);
            GUILayout.Label($"<color=#{Hex(PolicyColors[p])}>●</color> <b>{s.policy}</b>", textStyle, GUILayout.Width(36));
            bool ok = measured > 20;
            Cell(ok ? s.completed[step].ToString() : "–", 52);
            Cell(ok ? (100f * s.completed[step] / measured).ToString("0.0") : "–", 74);
            Cell(ok && s.completed[step] > 0 ? s.meanTime[step].ToString("0") : "–", 62);
            Cell(s.stuck[step].ToString(), 56);
            GUILayout.EndHorizontal();
            Rect row = GUILayoutUtility.GetLastRect();
            if (Event.current.type == EventType.MouseDown && row.Contains(Event.current.mousePosition) && p != policy)
            {
                ShowPolicy(p);
                Event.current.Use();
            }
        }
        GUILayout.Label("Tamam.: ısınmadan sonra tamamlanan sipariş · Ort. süre: siparişin gelişinden teslimine geçen adım. Satıra tıkla: o politikayı izle.", smallStyle);
        GUILayout.Space(10);

        // grafik
        GUILayout.Label($"Tamamlanan sipariş (ısınmadan sonra, en çok {chartMax})", smallStyle);
        Rect chart = GUILayoutUtility.GetRect(area.width - 28, ChartH / 2f);
        GUI.DrawTexture(chart, chartTex, ScaleMode.StretchToFill);
        float cx = chart.x + chart.width * step / LastFrame;
        GUI.DrawTexture(new Rect(cx - 1, chart.y, 2, chart.height), cursorTex);
        if (Event.current.type == EventType.MouseDrag || Event.current.type == EventType.MouseDown)
        {
            if (chart.Contains(Event.current.mousePosition))
            {
                Seek((Event.current.mousePosition.x - chart.x) / chart.width * LastFrame);
                Event.current.Use();
            }
        }
        string events = info.events.Length > 0 ? $"<color=#{Hex(Closed)}>■</color> olay süresi   " : "";
        GUILayout.Label($"<color=#{Hex(new Color(0.95f, 0.79f, 0.30f))}>■</color> ısınma   {events}grafiğe tıkla: o ana git", smallStyle);
        GUILayout.Space(10);

        // lejant
        GUILayout.Label(
            Legend("●", Moving, "ürün taşıyor") + Legend("○", Moving, "boş") + "\n"
            + Legend("●", Stuck, "ilerleyemiyor") + Legend("✕", Failed, "arızalı") + "\n"
            + Legend("◆", OrderColor, "bekleyen sipariş") + Legend("■", Closed, "kapalı hücre") + "\n"
            + Legend("■", Shelf, "raf") + Legend("■", Station, "paketleme masası") + Legend("■", ParkMark, "park"),
            textStyle);
        GUILayout.EndArea();
    }

    private void Header(string text, float width) =>
        GUILayout.Label(text, new GUIStyle(smallStyle) { alignment = TextAnchor.MiddleRight }, GUILayout.Width(width));

    private void Cell(string text, float width) => GUILayout.Label(text, cellStyle, GUILayout.Width(width));

    private void DrawBottomBar(float w, float h)
    {
        GUI.Box(new Rect(0, h - BottomBar, w, BottomBar), GUIContent.none, panelStyle);
        float y0 = h - BottomBar + 9;
        GUI.Label(new Rect(14, y0, 170, 20), $"Hız: <b>{stepsPerSecond:0.##}</b> adım/sn", textStyle);
        GUI.DrawTexture(new Rect(150, y0 + 9, 130, 4), trackTex);
        float logSpeed = GUI.HorizontalSlider(new Rect(150, y0 + 4, 130, 16),
            Mathf.Log(stepsPerSecond), Mathf.Log(MinSpeed), Mathf.Log(MaxSpeed));
        stepsPerSecond = Mathf.Exp(logSpeed);

        bool before = showArrows ^ showOrders ^ showHeat;
        showArrows = GUI.Toggle(new Rect(296, y0, 110, 20), showArrows, " Yön okları");
        showOrders = GUI.Toggle(new Rect(400, y0, 160, 20), showOrders, " Bekleyen siparişler");
        showHeat = GUI.Toggle(new Rect(550, y0, 190, 20), showHeat, " Sıkışıklık ısı haritası");
        if (before != (showArrows ^ showOrders ^ showHeat)) { heatFrame = -1; Apply(); }

        GUI.Label(new Rect(14, y0 + 28, 60, 20), "Zaman", textStyle);
        var bar = new Rect(70, y0 + 32, w - 84, 16);
        // zaman çubuğunda ısınma ve olay bölümleri gölgeli
        GUI.DrawTexture(new Rect(bar.x, bar.y + 3, bar.width, bar.height - 6), trackTex);
        GUI.DrawTexture(new Rect(bar.x, bar.y + 3, bar.width * run.warmup / LastFrame, bar.height - 6), warmupTex);
        foreach (var e in Info.events)
            GUI.DrawTexture(new Rect(bar.x + bar.width * e.start / LastFrame, bar.y + 3,
                                     bar.width * e.duration / LastFrame, bar.height - 6), eventTex);
        float newTime = GUI.HorizontalSlider(bar, time, 0f, LastFrame);
        if (!Mathf.Approximately(newTime, time)) Seek(newTime);

        GUI.Label(new Rect(750, y0, w - 764, 20),
            "<color=#9aa3ad>tıkla: robot ayrıntısı · tekerlek/sürükle: yakınlaştır/kaydır · boşluk: oynat · 1-4: politika</color>",
            smallStyle);
    }

    private void DrawCard(ReplayFrame fr)
    {
        int r = selected;
        int phase = fr.phase[r];
        bool broken = Array.IndexOf(fr.failed, r) >= 0;
        string state = fr.blocked[r] > 0
            ? $"<color=#ff6b6b><b>{fr.blocked[r]} adımdır ilerleyemiyor</b></color>"
            : "ilerliyor";
        if (phase == 0) state = "parkta bekliyor";
        if (broken) state = "<color=#c0c4ca><b>arızalı, yerinde duruyor</b></color>";

        string task = "görev yok";
        int oid = fr.order[r];
        if (oid >= 0)
        {
            var o = run.orders[oid];
            string drop = phase == 2 ? $"istasyon ({fr.tx[r]}, {fr.ty[r]})"
                        : run.policyId == "P3" ? "istasyon: ürün alınınca seçilecek"
                        : $"istasyon ({o.drop.x}, {o.drop.y})";
            task = $"Sipariş #{o.id} ({o.arrival}. adımda geldi)\nraf ({o.pick.x}, {o.pick.y}) → {drop}";
        }
        int remaining = 0;
        if (fr.plan[r] >= 0) remaining = run.plans[fr.plan[r]].xs.Length - fr.planOffset[r];

        GUILayout.BeginArea(CardRect(), cardStyle);
        GUILayout.Label($"Robot {r}", titleStyle);
        GUILayout.Space(4);
        GUILayout.Label($"<b>Ne yapıyor:</b> {PhaseNames[phase]}", textStyle);
        GUILayout.Label($"<b>Durum:</b> {state}", textStyle);
        GUILayout.Label($"<b>Görev:</b> {task}", textStyle);
        GUILayout.Label($"<b>Konum:</b> ({fr.xs[r]}, {fr.ys[r]})   <b>Hedef:</b> ({fr.tx[r]}, {fr.ty[r]})", textStyle);
        GUILayout.Label($"<b>Kalan rota:</b> {remaining} adım", textStyle);
        GUILayout.EndArea();
    }

    private static string Legend(string symbol, Color c, string label) =>
        $"<color=#{ColorUtility.ToHtmlStringRGB(c)}>{symbol}</color> {label}   ";
}
