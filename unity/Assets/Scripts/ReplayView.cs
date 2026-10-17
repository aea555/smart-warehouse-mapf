using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;

// replay.json'daki simülasyon kayıtlarını oynatır.
//
// Robotların hareketi Python simülasyonundan gelir (src/warehouse_mapf/sim.py). Unity sadece çizer.
//
// Haritada her robotun ürün taşıyıp taşımadığı (dolu/boş daire) ve ilerleyip ilerleyemediği
// (mavi/kırmızı) görünür. Robota tıklanınca rotası, hedefi ve görev bilgisi açılır, diğerleri soluklaşır.
//
// Kontroller: boşluk oynat/duraklat, sağ/sol ok tek adım, tekerlek yakınlaştır, sürükle kaydır,
// robota tıkla rotasını gör, Esc seçimi kaldır.
//
// Python'da y aşağı doğru artar, Unity'de yukarı. Bu yüzden y eksi ile çevrilir.
public class ReplayView : MonoBehaviour
{
    [SerializeField] private string replayFile = "replay.json";

    // renkler
    private static readonly Color Background = new Color(0.07f, 0.08f, 0.10f);
    private static readonly Color Floor      = new Color(0.17f, 0.19f, 0.23f);
    private static readonly Color Shelf      = new Color(0.72f, 0.47f, 0.22f);
    private static readonly Color Station    = new Color(0.20f, 0.65f, 0.60f);
    private static readonly Color DropMark   = new Color(0.20f, 0.65f, 0.60f, 0.35f);
    private static readonly Color ParkMark   = new Color(0.24f, 0.27f, 0.32f);
    private static readonly Color OrderColor = new Color(0.98f, 0.80f, 0.25f);
    private static readonly Color Moving     = new Color(0.36f, 0.66f, 1.00f);
    private static readonly Color Stuck      = new Color(1.00f, 0.30f, 0.30f);
    private static readonly Color Selected   = Color.white;

    private static readonly string[] PhaseNames = { "boşta", "toplamaya gidiyor", "ürünle teslimata gidiyor", "parka dönüyor" };

    // ekran düzeni, 720 piksel yüksekliğe göre
    private const float RefHeight = 720f;
    private const float TopBar = 92f;
    private const float BottomBar = 66f;

    private const float MinSpeed = 0.25f, MaxSpeed = 20f;
    private const float DimAlpha = 0.22f;

    private ReplaySet set;
    private ReplayRun run;
    private int current;
    private Transform world;
    private Sprite square, circle, hollow, ring, arrow;
    private Material spriteMaterial;

    private SpriteRenderer[] robots = new SpriteRenderer[0];
    private SpriteRenderer[] arrows = new SpriteRenderer[0];
    private readonly List<SpriteRenderer> orderPool = new List<SpriteRenderer>();
    private Transform orderRoot;

    // seçili robot
    private int selected = -1;
    private LineRenderer routeLine;
    private SpriteRenderer selectRing, targetMark;

    // katmanlar
    private bool showArrows;
    private bool showOrders = true;

    private float time;                 // kayıttaki yer, kesirli adım
    private bool playing;
    private float stepsPerSecond = 1f;
    private string loadError;

    private Camera cam;
    private float fitSize;
    private bool dragging;
    private Vector2 pressPos, lastMouse;

    private GUIStyle panelStyle, titleStyle, textStyle, statStyle, buttonStyle, cardStyle;

    // kurulum

    private void Start()
    {
        square = SpriteUtil.Square();
        circle = SpriteUtil.Circle();
        hollow = SpriteUtil.Ring(64, 0.38f);
        ring = SpriteUtil.Ring();
        arrow = SpriteUtil.Arrow();
        spriteMaterial = SpriteUtil.UnlitMaterial();
        cam = Camera.main;

        string file = Path.Combine(Application.streamingAssetsPath, replayFile);
        if (!File.Exists(file))
        {
            loadError = "replay.json bulunamadi. Once: uv run python tools/export_replay.py";
            return;
        }
        set = JsonUtility.FromJson<ReplaySet>(File.ReadAllText(file));
        if (set.runs == null || set.runs.Length == 0)
        {
            loadError = "replay.json icinde kayit yok.";
            return;
        }
        ShowRun(0);
    }

    public void ShowRun(int index)
    {
        current = (index + set.runs.Length) % set.runs.Length;
        run = set.runs[current];
        if (world != null) Destroy(world.gameObject);
        world = new GameObject("World").transform;
        selected = -1;
        Build();
        FitCamera();
        time = 0f;
        playing = false;
        Apply();
    }

    private static Vector3 World(float x, float y) => new Vector3(x, -y, 0f);

    private void Build()
    {
        var gridRoot = new GameObject("Grid").transform;
        gridRoot.SetParent(world, false);
        for (int y = 0; y < run.height; y++)
        for (int x = 0; x < run.width; x++)
            Spawn("Floor", square, World(x, y), Floor, 0.94f, 0, gridRoot);
        foreach (var c in run.parks) Spawn("Park", square, World(c.x, c.y), ParkMark, 0.94f, 1, gridRoot);
        foreach (var c in run.shelves) Spawn("Shelf", square, World(c.x, c.y), Shelf, 0.90f, 1, gridRoot);
        foreach (var c in run.stations) Spawn("Station", square, World(c.x, c.y), Station, 0.90f, 1, gridRoot);
        foreach (var c in run.drops) Spawn("Drop", square, World(c.x, c.y), DropMark, 0.94f, 1, gridRoot);

        orderRoot = new GameObject("Orders").transform;
        orderRoot.SetParent(world, false);
        orderPool.Clear();

        var robotRoot = new GameObject("Robots").transform;
        robotRoot.SetParent(world, false);
        int n = run.robots;
        robots = new SpriteRenderer[n];
        arrows = new SpriteRenderer[n];
        for (int i = 0; i < n; i++)
        {
            robots[i] = Spawn($"Robot {i}", circle, Vector3.zero, Moving, 0.72f, 5, robotRoot);
            arrows[i] = Child(robots[i], arrow, Color.white, 0.45f, 7);
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

    // haritanın tamamı üst ve alt panelin arasına sığsın
    private void FitCamera()
    {
        cam.orthographic = true;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Background;

        float free = 1f - (TopBar + BottomBar) / RefHeight;        // haritaya kalan ekran oranı
        const float margin = 0.8f;
        float sizeH = (run.height + margin) / (2f * free);
        float sizeW = (run.width + margin) / (2f * cam.aspect);
        fitSize = Mathf.Max(sizeH, sizeW);
        cam.orthographicSize = fitSize;

        float shift = (TopBar - BottomBar) / RefHeight * fitSize;
        cam.transform.position = new Vector3((run.width - 1) / 2f, -(run.height - 1) / 2f + shift, -10f);
    }

    private void HandleMouse()
    {
        var mouse = Mouse.current;
        if (mouse == null) return;
        Vector2 pos = mouse.position.ReadValue();
        float k = Screen.height / RefHeight;
        bool overCanvas = pos.y < Screen.height - TopBar * k && pos.y > BottomBar * k
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
        HandleMouse();

        var kb = Keyboard.current;
        if (kb != null)
        {
            if (kb.spaceKey.wasPressedThisFrame) TogglePlay();
            if (kb.rightArrowKey.wasPressedThisFrame) Seek(Mathf.Floor(time) + 1f);
            if (kb.leftArrowKey.wasPressedThisFrame) Seek(Mathf.Ceil(time) - 1f);
            if (kb.escapeKey.wasPressedThisFrame) Select(-1);
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

    // robotları, siparişleri ve seçimi şu anki zamana göre çizer
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

            // dolu daire ürün taşıyor, boş daire taşımıyor, kırmızı ilerleyemiyor
            robots[r].sprite = a.phase[r] == 2 ? circle : hollow;
            Color c = a.blocked[r] > 0 ? Stuck : Moving;
            if (focus && r != selected) c.a = DimAlpha;
            robots[r].color = c;

            int dx = a.nx[r] - a.xs[r], dy = a.ny[r] - a.ys[r];
            bool wants = (showArrows || r == selected) && (dx != 0 || dy != 0);
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

        int shown = showOrders ? a.openPicks.Length : 0;
        while (orderPool.Count < shown)
        {
            var d = Spawn("Order", square, Vector3.zero, OrderColor, 0.30f, 3, orderRoot);
            d.transform.rotation = Quaternion.Euler(0f, 0f, 45f);   // elmas gibi dursun
            orderPool.Add(d);
        }
        for (int k = 0; k < orderPool.Count; k++)
        {
            bool on = k < shown;
            orderPool[k].enabled = on;
            if (on)
            {
                orderPool[k].transform.position = World(a.openPicks[k].x, a.openPicks[k].y);
                orderPool[k].color = focus ? new Color(OrderColor.r, OrderColor.g, OrderColor.b, DimAlpha) : OrderColor;
            }
        }

        DrawSelection(a);
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

    // arayüz

    private void InitStyles()
    {
        if (panelStyle != null) return;
        panelStyle = new GUIStyle { normal = { background = Solid(new Color(0.04f, 0.045f, 0.06f, 0.96f)) }, padding = new RectOffset(14, 14, 8, 8) };
        cardStyle  = new GUIStyle { normal = { background = Solid(new Color(0.06f, 0.07f, 0.09f, 0.94f)) }, padding = new RectOffset(14, 14, 10, 10) };
        titleStyle = new GUIStyle { fontSize = 18, fontStyle = FontStyle.Bold, richText = true, normal = { textColor = Color.white } };
        textStyle  = new GUIStyle { fontSize = 13, richText = true, wordWrap = true, normal = { textColor = new Color(0.78f, 0.81f, 0.86f) } };
        statStyle  = new GUIStyle(textStyle) { fontSize = 15, wordWrap = false };
        buttonStyle = new GUIStyle(GUI.skin.button) { fontSize = 13, fixedHeight = 26 };
    }

    private Texture2D warmupTex;
    private Texture2D WarmupTex() => warmupTex != null ? warmupTex : (warmupTex = Solid(new Color(0.95f, 0.79f, 0.30f, 0.35f)));

    private static Texture2D Solid(Color c)
    {
        var t = new Texture2D(1, 1);
        t.SetPixel(0, 0, c);
        t.Apply();
        return t;
    }

    // kart robotun karşı tarafında durur, robotu ve rotasını örtmesin
    private Rect CardRect()
    {
        float w = Screen.width / (Screen.height / RefHeight);
        bool robotOnRight = selected >= 0 && cam.WorldToViewportPoint(robots[selected].transform.position).x > 0.5f;
        float x = robotOnRight ? 14f : w - 300f;
        return new Rect(x, TopBar + 12, 286, 150);
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

        var fr = run.frames[FrameIndex];
        int stuck = 0;
        foreach (int bl in fr.blocked) if (bl > 0) stuck++;

        // üst panelde senaryo ve anlık durum
        GUI.Box(new Rect(0, 0, w, TopBar), GUIContent.none, panelStyle);
        const float controlsW = 440f;
        GUILayout.BeginArea(new Rect(14, 8, w - controlsW - 40, TopBar - 12));
        GUILayout.Label($"{run.label}  <size=13><color=#9aa3ad>({current + 1}/{set.runs.Length})</color></size>", titleStyle);
        GUILayout.Label($"{run.policy}  ·  {run.robots} robot  ·  {run.rate:0.00} sipariş/adım  ·  raf yoğunluğu {run.density}  ·  seed {run.seed}", statStyle);
        GUILayout.Space(4);
        string phaseNote = FrameIndex < run.warmup ? " <color=#f2c94c>(ısınma)</color>" : "";
        GUILayout.Label($"Adım <b>{FrameIndex}</b>/{LastFrame}{phaseNote}   Tamamlanan <b>{fr.completed}</b>/{fr.arrived}   "
                      + $"Bekleyen <b>{fr.open}</b>   Çakışma <b>{fr.conflicts}</b>   "
                      + $"<color=#ff6b6b>Sıkışan robot <b>{stuck}</b></color>", statStyle);
        GUILayout.EndArea();

        GUILayout.BeginArea(new Rect(w - controlsW - 14, 10, controlsW, TopBar - 14));
        GUILayout.BeginHorizontal();
        if (GUILayout.Button("◀ Önceki kayıt", buttonStyle)) ShowRun(current - 1);
        if (GUILayout.Button("Sonraki kayıt ▶", buttonStyle)) ShowRun(current + 1);
        GUILayout.EndHorizontal();
        GUILayout.BeginHorizontal();
        if (GUILayout.Button(playing ? "❚❚ Duraklat" : "▶ Başlat", buttonStyle, GUILayout.Width(100))) TogglePlay();
        if (GUILayout.Button("◀ Adım", buttonStyle)) Seek(Mathf.Ceil(time) - 1f);
        if (GUILayout.Button("Adım ▶", buttonStyle)) Seek(Mathf.Floor(time) + 1f);
        if (GUILayout.Button("Isınmayı atla ⏭", buttonStyle, GUILayout.Width(120))) Seek(run.warmup);
        if (GUILayout.Button("Sığdır", buttonStyle)) FitCamera();
        GUILayout.EndHorizontal();
        GUILayout.EndArea();

        if (selected >= 0) DrawCard(fr);

        // alt panelde hız, zaman, katmanlar ve lejant
        GUI.Box(new Rect(0, h - BottomBar, w, BottomBar), GUIContent.none, panelStyle);
        float y0 = h - BottomBar + 8;
        GUI.Label(new Rect(14, y0, 170, 20), $"Hız: <b>{stepsPerSecond:0.##}</b> adım/sn", textStyle);
        float logSpeed = GUI.HorizontalSlider(new Rect(150, y0 + 4, 140, 16),
            Mathf.Log(stepsPerSecond), Mathf.Log(MinSpeed), Mathf.Log(MaxSpeed));
        stepsPerSecond = Mathf.Exp(logSpeed);

        bool arrowsBefore = showArrows, ordersBefore = showOrders;
        showArrows = GUI.Toggle(new Rect(305, y0, 130, 20), showArrows, " Yön okları");
        showOrders = GUI.Toggle(new Rect(425, y0, 170, 20), showOrders, " Bekleyen siparişler");
        if (arrowsBefore != showArrows || ordersBefore != showOrders) Apply();

        GUI.Label(new Rect(595, y0, 60, 20), "Zaman", textStyle);
        var bar = new Rect(645, y0 + 4, w - 659, 16);
        // zaman çubuğunda ısınma bölümü sarı gölgeli
        GUI.DrawTexture(new Rect(bar.x, bar.y + 3, bar.width * run.warmup / LastFrame, bar.height - 6), WarmupTex());
        float newTime = GUI.HorizontalSlider(bar, time, 0f, LastFrame);
        if (!Mathf.Approximately(newTime, time)) Seek(newTime);

        GUI.Label(new Rect(14, h - 30, w - 28, 22),
            Legend("●", Moving, "ürün taşıyor") + Legend("○", Moving, "boş") + Legend("●", Stuck, "sıkışmış (ilerleyemiyor)")
            + Legend("◆", OrderColor, "bekleyen sipariş") + Legend("■", Shelf, "raf") + Legend("■", Station, "paketleme")
            + $"{Legend("▬", new Color(0.95f, 0.79f, 0.30f), $"ısınma (ilk {run.warmup} adım, ölçüme dahil değil)")}"
            + "  <color=#9aa3ad>tıkla: robot ayrıntısı · tekerlek/sürükle: yakınlaştır/kaydır · boşluk: oynat</color>", statStyle);
    }

    private void DrawCard(ReplayFrame fr)
    {
        int r = selected;
        int phase = fr.phase[r];
        string state = fr.blocked[r] > 0
            ? $"<color=#ff6b6b><b>{fr.blocked[r]} adımdır ilerleyemiyor</b></color>"
            : "ilerliyor";
        if (phase == 0) state = "parkta bekliyor";

        string task = "görev yok";
        int oid = fr.order[r];
        if (oid >= 0)
        {
            var o = run.orders[oid];
            task = $"Sipariş #{o.id} ({o.arrival}. adımda geldi)\nraf ({o.pick.x}, {o.pick.y}) → istasyon ({o.drop.x}, {o.drop.y})";
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
