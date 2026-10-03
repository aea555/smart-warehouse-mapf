using System.Collections.Generic;
using System.IO;
using UnityEngine;

// scene.json'dan rastgele bir senaryo seçip çizer, robotu yol boyunca yürütür.
// "Yeni görev" başka bir senaryoya geçer.
//
// Yolu A* Python tarafında buluyor (src/warehouse_mapf/astar.py). Unity sadece çizer.
//
// Python'da y aşağı doğru artar, Unity'de yukarı. Bu yüzden y eksi ile çevrilir.
public class WarehouseView : MonoBehaviour
{
    [SerializeField] private string sceneFile = "scene.json";
    [SerializeField] private float cellsPerSecond = 3f;

    // renkler
    private static readonly Color Background = new Color(0.07f, 0.08f, 0.10f);
    private static readonly Color Floor      = new Color(0.17f, 0.19f, 0.23f);
    private static readonly Color Shelf      = new Color(0.72f, 0.47f, 0.22f);
    private static readonly Color Obstacle   = new Color(0.62f, 0.26f, 0.28f);
    private static readonly Color PathDot    = new Color(0.30f, 0.85f, 0.85f);
    private static readonly Color StartColor = new Color(0.35f, 0.80f, 0.40f);
    private static readonly Color GoalColor  = new Color(0.98f, 0.80f, 0.25f);
    private static readonly Color RobotColor = new Color(0.30f, 0.62f, 1.00f);

    private ScenarioSet set;
    private Scenario data;
    private int current = -1;
    private Transform world;
    private Sprite square;
    private Sprite circle;
    private Material spriteMaterial;
    private Transform robot;
    private Vector3[] waypoints = new Vector3[0];

    private float progress;      // yolda kaç hücre ilerledi, kesirli
    private bool playing;
    private float speed = 1f;
    private string loadError;

    private GUIStyle panelStyle, titleStyle, textStyle, buttonStyle, activeButtonStyle;

    // kurulum

    private void Start()
    {
        square = MakeSquareSprite();
        circle = MakeCircleSprite(64);

        var unlit = Shader.Find("Universal Render Pipeline/2D/Sprite-Unlit-Default");
        if (unlit != null) spriteMaterial = new Material(unlit);

        if (!Load()) return;
        NewTask();
    }

    private bool Load()
    {
        string file = Path.Combine(Application.streamingAssetsPath, sceneFile);
        if (!File.Exists(file))
        {
            loadError = "scene.json bulunamadi. Once: uv run python tools/export_scene.py";
            return false;
        }
        set = JsonUtility.FromJson<ScenarioSet>(File.ReadAllText(file));
        if (set.scenarios == null || set.scenarios.Length == 0)
        {
            loadError = "scene.json icinde senaryo yok.";
            return false;
        }
        return true;
    }

    // şu ankinden farklı rastgele bir senaryo
    public void NewTask()
    {
        int next = Random.Range(0, set.scenarios.Length);
        if (set.scenarios.Length > 1)
            while (next == current) next = Random.Range(0, set.scenarios.Length);
        ShowTask(next);
    }

    // belirli bir senaryoyu göster, index 0'dan başlar
    public void ShowTask(int index)
    {
        current = Mathf.Clamp(index, 0, set.scenarios.Length - 1);
        data = set.scenarios[current];

        if (world != null) Destroy(world.gameObject);
        world = new GameObject("World").transform;
        Build();
        FitCamera();
        ResetRun();
    }

    private static Vector3 World(int x, int y) => new Vector3(x, -y, 0f);

    private void Build()
    {
        var shelves = new HashSet<Vector2Int>();
        foreach (var c in data.shelves) shelves.Add(new Vector2Int(c.x, c.y));
        var obstacles = new HashSet<Vector2Int>();
        foreach (var c in data.obstacles) obstacles.Add(new Vector2Int(c.x, c.y));

        var gridRoot = new GameObject("Grid").transform;
        gridRoot.SetParent(world, false);
        for (int y = 0; y < data.height; y++)
        for (int x = 0; x < data.width; x++)
        {
            var cell = new Vector2Int(x, y);
            Spawn("Floor", square, World(x, y), Floor, 0.94f, 0, gridRoot);
            if (shelves.Contains(cell))
                Spawn("Shelf", square, World(x, y), Shelf, 0.90f, 1, gridRoot);
            else if (obstacles.Contains(cell))
                Spawn("Obstacle", square, World(x, y), Obstacle, 0.62f, 1, gridRoot);
        }

        var pathRoot = new GameObject("Path").transform;
        pathRoot.SetParent(world, false);
        var points = new List<Vector3>();
        foreach (var c in data.path)
        {
            Vector3 p = World(c.x, c.y);
            points.Add(p);
            Spawn("PathDot", circle, p, PathDot, 0.26f, 2, pathRoot);
        }
        waypoints = points.ToArray();

        Spawn("Start", square, World(data.start.x, data.start.y), StartColor, 0.72f, 3, world);
        var goal = Spawn("Goal", square, World(data.goal.x, data.goal.y), GoalColor, 0.58f, 3, world);
        goal.transform.rotation = Quaternion.Euler(0f, 0f, 45f);   // elmas gibi dursun

        robot = Spawn("Robot", circle, World(data.start.x, data.start.y), RobotColor, 0.72f, 5, world).transform;
    }

    private GameObject Spawn(string name, Sprite sprite, Vector3 pos, Color color,
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
        return go;
    }

    private void FitCamera()
    {
        var cam = Camera.main;
        cam.orthographic = true;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Background;

        const float margin = 1.2f;
        const float topBarWorld = 2.2f;   // üst panel için yer
        float halfH = data.height / 2f + margin + topBarWorld / 2f;
        float halfW = data.width / 2f + margin;
        cam.orthographicSize = Mathf.Max(halfH, halfW / cam.aspect);
        cam.transform.position = new Vector3((data.width - 1) / 2f,
                                             -(data.height - 1) / 2f + topBarWorld / 2f, -10f);
    }

    // hareket

    private void Update()
    {
        if (!playing || waypoints.Length < 2) return;
        progress += cellsPerSecond * speed * Time.deltaTime;
        float end = waypoints.Length - 1;
        if (progress >= end) { progress = end; playing = false; }
        robot.position = Sample(progress);
    }

    private Vector3 Sample(float t)
    {
        int i = Mathf.Clamp((int)t, 0, waypoints.Length - 2);
        return Vector3.Lerp(waypoints[i], waypoints[i + 1], t - i);
    }

    public void ResetRun()
    {
        progress = 0f;
        playing = false;
        if (waypoints.Length > 0) robot.position = waypoints[0];
    }

    public void StepOnce()
    {
        if (waypoints.Length < 2) return;
        playing = false;
        progress = Mathf.Min(Mathf.Floor(progress) + 1f, waypoints.Length - 1);
        robot.position = Sample(progress);
    }

    public void Play() { if (progress >= waypoints.Length - 1) ResetRun(); playing = true; }
    public void SetSpeed(float s) => speed = s;

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
        buttonStyle = new GUIStyle(GUI.skin.button) { fontSize = 14, fixedHeight = 30 };
        activeButtonStyle = new GUIStyle(buttonStyle) { fontStyle = FontStyle.Bold, normal = { textColor = GoalColor } };
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
            GUI.Label(new Rect(20, 20, 800, 40), loadError, titleStyle);
            return;
        }

        int total = Mathf.Max(0, waypoints.Length - 1);
        int done = Mathf.FloorToInt(progress + 0.0001f);
        string state = done >= total ? "Hedefte"
                     : playing ? "Hareket ediyor" : "Bekliyor";

        GUILayout.BeginArea(new Rect(0, 0, w, 84), panelStyle);
        GUILayout.BeginHorizontal();

        GUILayout.BeginVertical(GUILayout.Width(640));
        GUILayout.Label("Smart Warehouse — A* (tek robot)", titleStyle);
        GUILayout.Space(6);
        GUILayout.Label($"Görev {current + 1}/{set.scenarios.Length} (seed {data.seed})   |   Yol: {waypoints.Length} hücre, {total} adım   |   Robot: {done}/{total}   |   {state}", textStyle);
        GUILayout.EndVertical();

        GUILayout.FlexibleSpace();

        if (GUILayout.Button(playing ? "Duraklat" : "Başlat", buttonStyle, GUILayout.Width(100)))
        {
            if (done >= total) ResetRun();
            playing = !playing;
        }
        if (GUILayout.Button("Adım", buttonStyle, GUILayout.Width(80))) StepOnce();
        if (GUILayout.Button("Sıfırla", buttonStyle, GUILayout.Width(80))) ResetRun();
        if (GUILayout.Button("Yeni görev", buttonStyle, GUILayout.Width(110))) NewTask();

        GUILayout.Space(16);
        foreach (float s in new[] { 1f, 2f, 4f })
        {
            var style = Mathf.Approximately(speed, s) ? activeButtonStyle : buttonStyle;
            if (GUILayout.Button($"{s:0}x", style, GUILayout.Width(48))) speed = s;
        }

        GUILayout.EndHorizontal();
        GUILayout.EndArea();

        // lejant
        GUILayout.BeginArea(new Rect(16, h - 36, w - 32, 30));
        GUILayout.Label(Legend("■", Shelf, "raf") + Legend("■", Obstacle, "engel") + Legend("●", PathDot, "rota") + Legend("■", StartColor, "başlangıç")
                      + Legend("◆", GoalColor, "hedef") + Legend("●", RobotColor, "robot"), textStyle);
        GUILayout.EndArea();
    }

    private static string Legend(string symbol, Color c, string label) =>
        $"<color=#{ColorUtility.ToHtmlStringRGB(c)}>{symbol}</color> {label}      ";

    // sprite üretimi

    private static Sprite MakeSquareSprite()
    {
        var tex = new Texture2D(4, 4) { filterMode = FilterMode.Point };
        var px = new Color[16];
        for (int i = 0; i < px.Length; i++) px[i] = Color.white;
        tex.SetPixels(px);
        tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, 4, 4), new Vector2(0.5f, 0.5f), 4f);
    }

    private static Sprite MakeCircleSprite(int res)
    {
        var tex = new Texture2D(res, res) { filterMode = FilterMode.Bilinear };
        float r = res / 2f;
        for (int y = 0; y < res; y++)
        for (int x = 0; x < res; x++)
        {
            float d = Vector2.Distance(new Vector2(x + 0.5f, y + 0.5f), new Vector2(r, r));
            float a = Mathf.Clamp01(r - d);   // kenarda 1 piksellik yumuşatma
            tex.SetPixel(x, y, new Color(1f, 1f, 1f, a));
        }
        tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, res, res), new Vector2(0.5f, 0.5f), res);
    }
}
