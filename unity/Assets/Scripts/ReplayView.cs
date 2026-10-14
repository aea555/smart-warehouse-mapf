using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;

// replay.json'daki simülasyon kayıtlarını oynatır.
//
// Robotların hareketi Python simülasyonundan gelir (src/warehouse_mapf/sim.py). Unity sadece çizer.
//
// Kontroller: boşluk oynat/duraklat, sağ/sol ok tek adım, tekerlek yakınlaştır, sürükle kaydır.
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
    private static readonly Color Idle       = new Color(0.55f, 0.58f, 0.63f);
    private static readonly Color ToPick     = new Color(0.30f, 0.62f, 1.00f);
    private static readonly Color ToDrop     = new Color(0.35f, 0.80f, 0.40f);
    private static readonly Color ToHome     = new Color(0.62f, 0.55f, 0.85f);
    private static readonly Color Stuck      = new Color(1.00f, 0.25f, 0.25f);
    private static readonly Color[] PhaseColors = { Idle, ToPick, ToDrop, ToHome };

    // ekran düzeni, 720 piksel yüksekliğe göre
    private const float RefHeight = 720f;
    private const float TopBar = 92f;
    private const float BottomBar = 66f;

    private const float MinSpeed = 0.25f, MaxSpeed = 20f;

    private ReplaySet set;
    private ReplayRun run;
    private int current;
    private Transform world;
    private Sprite square, circle, ring, arrow;
    private Material spriteMaterial;

    private SpriteRenderer[] robots = new SpriteRenderer[0];
    private SpriteRenderer[] cargo = new SpriteRenderer[0];
    private SpriteRenderer[] arrows = new SpriteRenderer[0];
    private SpriteRenderer[] rings = new SpriteRenderer[0];
    private readonly List<SpriteRenderer> orderPool = new List<SpriteRenderer>();
    private Transform orderRoot;

    private float time;                 // kayıttaki yer, kesirli adım
    private bool playing;
    private float stepsPerSecond = 1f;
    private string loadError;

    private Camera cam;
    private float fitSize;
    private bool dragging;
    private Vector2 lastMouse;

    private GUIStyle panelStyle, titleStyle, textStyle, statStyle, buttonStyle;

    // kurulum

    private void Start()
    {
        square = SpriteUtil.Square();
        circle = SpriteUtil.Circle();
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
        cargo = new SpriteRenderer[n];
        arrows = new SpriteRenderer[n];
        rings = new SpriteRenderer[n];
        for (int i = 0; i < n; i++)
        {
            robots[i] = Spawn($"Robot {i}", circle, Vector3.zero, Idle, 0.70f, 5, robotRoot);
            cargo[i] = Child(robots[i], square, OrderColor, 0.42f, 6);
            rings[i] = Child(robots[i], ring, Stuck, 1.55f, 4);
            arrows[i] = Child(robots[i], arrow, Color.white, 0.45f, 7);
        }
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
        var sr = Spawn(sprite.name, sprite, Vector3.zero, color, scale, order, parent.transform);
        sr.transform.localPosition = Vector3.zero;
        sr.transform.localScale = new Vector3(scale, scale, 1f);
        return sr;
    }

    // kamera

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

        // üst panel daha kalın, harita iki panelin arasına ortalanır
        float shift = (TopBar - BottomBar) / RefHeight * fitSize;
        cam.transform.position = new Vector3((run.width - 1) / 2f, -(run.height - 1) / 2f + shift, -10f);
    }

    private void HandleCamera()
    {
        var mouse = Mouse.current;
        if (mouse == null) return;
        Vector2 pos = mouse.position.ReadValue();
        float k = Screen.height / RefHeight;
        bool overCanvas = pos.y < Screen.height - TopBar * k && pos.y > BottomBar * k;

        float scroll = mouse.scroll.ReadValue().y;
        if (overCanvas && Mathf.Abs(scroll) > 0.01f)
        {
            Vector3 before = cam.ScreenToWorldPoint(pos);
            float factor = scroll > 0 ? 0.88f : 1f / 0.88f;
            cam.orthographicSize = Mathf.Clamp(cam.orthographicSize * factor, 3f, fitSize * 1.5f);
            Vector3 after = cam.ScreenToWorldPoint(pos);
            cam.transform.position += before - after;   // imlecin altındaki nokta yerinde kalsın
        }

        if (mouse.leftButton.wasPressedThisFrame && overCanvas) { dragging = true; lastMouse = pos; }
        if (!mouse.leftButton.isPressed) dragging = false;
        if (dragging)
        {
            Vector3 delta = cam.ScreenToWorldPoint(lastMouse) - cam.ScreenToWorldPoint(pos);
            cam.transform.position += new Vector3(delta.x, delta.y, 0f);
            lastMouse = pos;
        }
    }

    // oynatma

    private int LastFrame => run.frames.Length - 1;

    private void Update()
    {
        if (run == null) return;
        HandleCamera();

        var kb = Keyboard.current;
        if (kb != null)
        {
            if (kb.spaceKey.wasPressedThisFrame) TogglePlay();
            if (kb.rightArrowKey.wasPressedThisFrame) Seek(Mathf.Floor(time) + 1f);
            if (kb.leftArrowKey.wasPressedThisFrame) Seek(Mathf.Ceil(time) - 1f);
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

    // robotları ve siparişleri şu anki zamana göre yerleştirir
    private void Apply()
    {
        int i = Mathf.Clamp(Mathf.FloorToInt(time), 0, LastFrame);
        int j = Mathf.Min(i + 1, LastFrame);
        float f = Mathf.SmoothStep(0f, 1f, time - i);   // hücreden hücreye yumuşak geçiş
        var a = run.frames[i];
        var b = run.frames[j];

        for (int r = 0; r < robots.Length; r++)
        {
            float x = Mathf.Lerp(a.xs[r], b.xs[r], f);
            float y = Mathf.Lerp(a.ys[r], b.ys[r], f);
            robots[r].transform.position = World(x, y);
            robots[r].color = PhaseColors[a.phase[r]];
            cargo[r].enabled = a.phase[r] == 2;

            bool stuck = a.blocked[r] > 0;
            rings[r].enabled = stuck;
            if (stuck) rings[r].color = new Color(Stuck.r, Stuck.g, Stuck.b, Mathf.Clamp01(0.45f + 0.2f * a.blocked[r]));

            // ok robotun gitmek istediği yöne bakar
            int dx = a.nx[r] - a.xs[r], dy = a.ny[r] - a.ys[r];
            bool wants = dx != 0 || dy != 0;
            arrows[r].enabled = wants;
            if (wants)
            {
                var dir = new Vector3(dx, -dy, 0f);
                arrows[r].transform.localPosition = dir * 0.62f;
                arrows[r].transform.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(-dy, dx) * Mathf.Rad2Deg);
                arrows[r].color = stuck ? Stuck : Color.white;
            }
        }

        while (orderPool.Count < a.openPicks.Length)
        {
            var d = Spawn("Order", square, Vector3.zero, OrderColor, 0.30f, 3, orderRoot);
            d.transform.rotation = Quaternion.Euler(0f, 0f, 45f);   // elmas gibi dursun
            orderPool.Add(d);
        }
        for (int k = 0; k < orderPool.Count; k++)
        {
            bool on = k < a.openPicks.Length;
            orderPool[k].enabled = on;
            if (on) orderPool[k].transform.position = World(a.openPicks[k].x, a.openPicks[k].y);
        }
    }

    // arayüz

    private void InitStyles()
    {
        if (panelStyle != null) return;
        var bg = new Texture2D(1, 1);
        bg.SetPixel(0, 0, new Color(0.04f, 0.045f, 0.06f, 0.96f));
        bg.Apply();
        panelStyle = new GUIStyle { normal = { background = bg }, padding = new RectOffset(14, 14, 8, 8) };
        titleStyle = new GUIStyle { fontSize = 18, fontStyle = FontStyle.Bold, normal = { textColor = Color.white } };
        textStyle  = new GUIStyle { fontSize = 13, richText = true, normal = { textColor = new Color(0.78f, 0.81f, 0.86f) } };
        statStyle  = new GUIStyle(textStyle) { fontSize = 15 };
        buttonStyle = new GUIStyle(GUI.skin.button) { fontSize = 13, fixedHeight = 26 };
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

        var fr = run.frames[Mathf.Clamp(Mathf.FloorToInt(time), 0, LastFrame)];
        int stuck = 0;
        foreach (int bl in fr.blocked) if (bl > 0) stuck++;

        // üst panelde senaryo ve anlık durum
        GUI.Box(new Rect(0, 0, w, TopBar), GUIContent.none, panelStyle);
        GUILayout.BeginArea(new Rect(14, 8, w - 28, TopBar - 12));
        GUILayout.BeginHorizontal();
        GUILayout.BeginVertical();
        GUILayout.Label($"{run.label}  <size=13><color=#9aa3ad>({current + 1}/{set.runs.Length})</color></size>", new GUIStyle(titleStyle) { richText = true });
        GUILayout.Label($"{run.policy}  ·  {run.robots} robot  ·  {run.rate:0.00} sipariş/adım  ·  raf yoğunluğu {run.density}  ·  seed {run.seed}", textStyle);
        GUILayout.Space(4);
        GUILayout.Label($"Adım <b>{Mathf.FloorToInt(time)}</b>/{LastFrame}     Tamamlanan <b>{fr.completed}</b>/{fr.arrived}     "
                      + $"Bekleyen sipariş <b>{fr.open}</b>     Çakışma <b>{fr.conflicts}</b>     "
                      + $"<color=#ff6b6b>İlerleyemeyen robot <b>{stuck}</b></color>", statStyle);
        GUILayout.EndVertical();
        GUILayout.FlexibleSpace();
        GUILayout.BeginVertical(GUILayout.Width(330));
        GUILayout.BeginHorizontal();
        if (GUILayout.Button("◀ Önceki kayıt", buttonStyle)) ShowRun(current - 1);
        if (GUILayout.Button("Sonraki kayıt ▶", buttonStyle)) ShowRun(current + 1);
        GUILayout.EndHorizontal();
        GUILayout.BeginHorizontal();
        if (GUILayout.Button(playing ? "❚❚ Duraklat" : "▶ Başlat", buttonStyle, GUILayout.Width(110))) TogglePlay();
        if (GUILayout.Button("◀ Adım", buttonStyle)) Seek(Mathf.Ceil(time) - 1f);
        if (GUILayout.Button("Adım ▶", buttonStyle)) Seek(Mathf.Floor(time) + 1f);
        if (GUILayout.Button("Sığdır", buttonStyle)) FitCamera();
        GUILayout.EndHorizontal();
        GUILayout.EndVertical();
        GUILayout.EndHorizontal();
        GUILayout.EndArea();

        // alt panelde hız, zaman çizelgesi ve lejant
        GUI.Box(new Rect(0, h - BottomBar, w, BottomBar), GUIContent.none, panelStyle);
        GUI.Label(new Rect(14, h - BottomBar + 8, 170, 20), $"Hız: <b>{stepsPerSecond:0.##}</b> adım/sn", textStyle);
        float logSpeed = GUI.HorizontalSlider(new Rect(150, h - BottomBar + 12, 150, 16),
            Mathf.Log(stepsPerSecond), Mathf.Log(MinSpeed), Mathf.Log(MaxSpeed));
        stepsPerSecond = Mathf.Exp(logSpeed);

        GUI.Label(new Rect(320, h - BottomBar + 8, 60, 20), "Zaman", textStyle);
        float newTime = GUI.HorizontalSlider(new Rect(370, h - BottomBar + 12, w - 384, 16), time, 0f, LastFrame);
        if (!Mathf.Approximately(newTime, time)) Seek(newTime);

        GUI.Label(new Rect(14, h - 30, w - 28, 22),
            Legend("●", Idle, "boşta") + Legend("●", ToPick, "toplamaya gidiyor") + Legend("●", ToDrop, "ürünle teslimata gidiyor")
            + Legend("●", ToHome, "parka dönüyor") + Legend("➤", Color.white, "gitmek istediği yön") + Legend("◯", Stuck, "ilerleyemiyor")
            + Legend("◆", OrderColor, "bekleyen sipariş") + Legend("■", Shelf, "raf") + Legend("■", Station, "paketleme")
            + "   <color=#9aa3ad>tekerlek: yakınlaştır · sürükle: kaydır · boşluk: başlat/duraklat</color>", textStyle);
    }

    private static string Legend(string symbol, Color c, string label) =>
        $"<color=#{ColorUtility.ToHtmlStringRGB(c)}>{symbol}</color> {label}   ";
}
