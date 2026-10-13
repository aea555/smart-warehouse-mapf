using System.Collections.Generic;
using System.IO;
using UnityEngine;

// replay.json'daki simülasyon kayıtlarını oynatır.
//
// Robotların hareketi Python simülasyonundan gelir (src/warehouse_mapf/sim.py). Unity sadece çizer.
//
// Python'da y aşağı doğru artar, Unity'de yukarı. Bu yüzden y eksi ile çevrilir.
public class ReplayView : MonoBehaviour
{
    [SerializeField] private string replayFile = "replay.json";
    [SerializeField] private float stepsPerSecond = 4f;

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
    private static readonly Color Stuck      = new Color(0.95f, 0.30f, 0.30f);
    private static readonly Color[] PhaseColors = { Idle, ToPick, ToDrop, ToHome };

    private ReplaySet set;
    private ReplayRun run;
    private int current;
    private Transform world;
    private Sprite square, circle;
    private Material spriteMaterial;

    private SpriteRenderer[] robots = new SpriteRenderer[0];
    private SpriteRenderer[] cargo = new SpriteRenderer[0];
    private readonly List<SpriteRenderer> orderPool = new List<SpriteRenderer>();
    private Transform orderRoot;

    private float time;          // kayıttaki yer, kesirli adım
    private bool playing;
    private float speed = 1f;
    private string loadError;

    private GUIStyle panelStyle, titleStyle, textStyle, statStyle, buttonStyle, activeButtonStyle;

    // kurulum

    private void Start()
    {
        square = SpriteUtil.Square();
        circle = SpriteUtil.Circle();
        spriteMaterial = SpriteUtil.UnlitMaterial();

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
        robots = new SpriteRenderer[run.robots];
        cargo = new SpriteRenderer[run.robots];
        for (int i = 0; i < run.robots; i++)
        {
            robots[i] = Spawn($"Robot {i}", circle, Vector3.zero, Idle, 0.78f, 5, robotRoot);
            cargo[i] = Spawn("Cargo", square, Vector3.zero, OrderColor, 0.36f, 6, robots[i].transform);
            cargo[i].transform.localPosition = Vector3.zero;
            cargo[i].transform.localScale = new Vector3(0.42f, 0.42f, 1f);
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

    private void FitCamera()
    {
        var cam = Camera.main;
        cam.orthographic = true;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Background;

        const float margin = 1.0f;
        const float topBarWorld = 5.0f;     // üst panel için yer
        const float bottomBarWorld = 2.6f;  // alt panel için yer
        float halfH = run.height / 2f + margin + (topBarWorld + bottomBarWorld) / 2f;
        float halfW = run.width / 2f + margin;
        cam.orthographicSize = Mathf.Max(halfH, halfW / cam.aspect);
        cam.transform.position = new Vector3((run.width - 1) / 2f,
            -(run.height - 1) / 2f + (topBarWorld - bottomBarWorld) / 2f, -10f);
    }

    // oynatma

    private int LastFrame => run.frames.Length - 1;

    private void Update()
    {
        if (run == null || !playing) return;
        time += stepsPerSecond * speed * Time.deltaTime;
        if (time >= LastFrame) { time = LastFrame; playing = false; }
        Apply();
    }

    // robotları ve siparişleri şu anki zamana göre yerleştirir
    private void Apply()
    {
        int i = Mathf.Clamp(Mathf.FloorToInt(time), 0, LastFrame);
        int j = Mathf.Min(i + 1, LastFrame);
        float f = time - i;
        var a = run.frames[i];
        var b = run.frames[j];

        for (int r = 0; r < robots.Length; r++)
        {
            float x = Mathf.Lerp(a.xs[r], b.xs[r], f);
            float y = Mathf.Lerp(a.ys[r], b.ys[r], f);
            robots[r].transform.position = World(x, y);
            Color c = PhaseColors[a.phase[r]];
            if (a.blocked[r] > 0) c = Color.Lerp(c, Stuck, Mathf.Clamp01(a.blocked[r] / 3f));
            robots[r].color = c;
            cargo[r].enabled = a.phase[r] == 2;
        }

        while (orderPool.Count < a.openPicks.Length)
        {
            var d = Spawn("Order", square, Vector3.zero, OrderColor, 0.40f, 3, orderRoot);
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

    private void StepOnce()
    {
        playing = false;
        time = Mathf.Min(Mathf.Floor(time) + 1f, LastFrame);
        Apply();
    }

    // arayüz

    private void InitStyles()
    {
        if (panelStyle != null) return;
        var bg = new Texture2D(1, 1);
        bg.SetPixel(0, 0, new Color(0.04f, 0.045f, 0.06f, 1f));
        bg.Apply();
        panelStyle = new GUIStyle { normal = { background = bg }, padding = new RectOffset(16, 16, 10, 10) };
        titleStyle = new GUIStyle { fontSize = 20, fontStyle = FontStyle.Bold, normal = { textColor = Color.white } };
        textStyle  = new GUIStyle { fontSize = 15, richText = true, normal = { textColor = new Color(0.80f, 0.83f, 0.88f) } };
        statStyle  = new GUIStyle(textStyle) { fontSize = 16 };
        buttonStyle = new GUIStyle(GUI.skin.button) { fontSize = 14, fixedHeight = 30 };
        activeButtonStyle = new GUIStyle(buttonStyle) { fontStyle = FontStyle.Bold, normal = { textColor = OrderColor } };
    }

    private const float RefHeight = 720f;

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
        int waiting = 0;
        foreach (int bl in fr.blocked) if (bl > 0) waiting++;

        GUILayout.BeginArea(new Rect(0, 0, w, 112), panelStyle);
        GUILayout.BeginHorizontal();
        GUILayout.BeginVertical(GUILayout.Width(700));
        GUILayout.Label($"Smart Warehouse — {run.label}", titleStyle);
        GUILayout.Space(4);
        GUILayout.Label($"{run.policy}   |   {run.robots} robot, {run.rate:0.00} sipariş/adım, raf yoğunluğu: {run.density}, seed {run.seed}", textStyle);
        GUILayout.Space(6);
        GUILayout.Label($"Adım <b>{Mathf.FloorToInt(time)}</b>/{LastFrame}     Tamamlanan <b>{fr.completed}</b>/{fr.arrived}     Bekleyen sipariş <b>{fr.open}</b>     "
                      + $"Çakışma <b>{fr.conflicts}</b>     İlerleyemeyen robot <b>{waiting}</b>", statStyle);
        GUILayout.EndVertical();
        GUILayout.FlexibleSpace();

        GUILayout.BeginVertical();
        GUILayout.BeginHorizontal();
        if (GUILayout.Button("◀ Önceki", buttonStyle, GUILayout.Width(96))) ShowRun(current - 1);
        GUILayout.Label($"{current + 1}/{set.runs.Length}", textStyle, GUILayout.Width(40));
        if (GUILayout.Button("Sonraki ▶", buttonStyle, GUILayout.Width(96))) ShowRun(current + 1);
        GUILayout.EndHorizontal();
        GUILayout.BeginHorizontal();
        if (GUILayout.Button(playing ? "Duraklat" : "Başlat", buttonStyle, GUILayout.Width(96)))
        {
            if (time >= LastFrame) time = 0f;
            playing = !playing;
        }
        if (GUILayout.Button("Adım", buttonStyle, GUILayout.Width(64))) StepOnce();
        if (GUILayout.Button("Sıfırla", buttonStyle, GUILayout.Width(72))) { time = 0f; playing = false; Apply(); }
        foreach (float s in new[] { 1f, 4f, 16f })
        {
            var style = Mathf.Approximately(speed, s) ? activeButtonStyle : buttonStyle;
            if (GUILayout.Button($"{s:0}x", style, GUILayout.Width(48))) speed = s;
        }
        GUILayout.EndHorizontal();
        GUILayout.EndVertical();
        GUILayout.EndHorizontal();
        GUILayout.EndArea();

        // zaman çizelgesi
        float newTime = GUI.HorizontalSlider(new Rect(16, h - 62, w - 32, 20), time, 0f, LastFrame);
        if (!Mathf.Approximately(newTime, time)) { time = newTime; Apply(); }

        // lejant
        GUILayout.BeginArea(new Rect(16, h - 36, w - 32, 30));
        GUILayout.Label(Legend("●", Idle, "boşta") + Legend("●", ToPick, "toplamaya gidiyor") + Legend("●", ToDrop, "teslimata gidiyor")
                      + Legend("●", ToHome, "parka dönüyor") + Legend("●", Stuck, "ilerleyemiyor") + Legend("◆", OrderColor, "bekleyen sipariş")
                      + Legend("■", Shelf, "raf") + Legend("■", Station, "paketleme"), textStyle);
        GUILayout.EndArea();
    }

    private static string Legend(string symbol, Color c, string label) =>
        $"<color=#{ColorUtility.ToHtmlStringRGB(c)}>{symbol}</color> {label}    ";
}
