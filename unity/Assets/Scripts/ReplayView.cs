using System.IO;
using UnityEngine;
using UnityEngine.InputSystem;

// Kayıtları iki harita yan yana olacak şekilde oynatır. İki harita aynı senaryonun (aynı siparişler)
// farklı politikalarla kaydıdır ve aynı adımda durur, böylece fark gözle görülür.
//
// Robotların hareketi Python simülasyonundan gelir (src/warehouse_mapf/sim.py). Unity sadece çizer.
//
// Kontroller: boşluk oynat/duraklat, sağ/sol ok tek adım, tekerlek yakınlaştır, sürükle kaydır,
// robota tıkla rotasını gör, Esc seçimi kaldır, H ısı haritası.
//
// Python'da y aşağı doğru artar, Unity'de yukarı. Bu yüzden y eksi ile çevrilir.
public class ReplayView : MonoBehaviour
{
    [SerializeField] string replayFolder = "replays";

    static readonly Color[] PolicyColors =
    {
        new Color(0.82f, 0.29f, 0.36f), new Color(0.24f, 0.60f, 0.80f),
        new Color(0.93f, 0.68f, 0.29f), new Color(0.66f, 0.55f, 0.98f),
    };
    static readonly string[] PhaseNames = { "boşta", "rafa gidiyor", "ürünü masaya götürüyor", "parka dönüyor" };
    static readonly float[] Speeds = { 1f, 3f, 10f, 30f };

    // ekran düzeni, 720 piksel yüksekliğe göre
    const float RefHeight = 720f;
    const float TopBar = 52f, PaneHeader = 40f, PaneFooter = 78f, BottomBar = 56f, Gap = 4f;

    ReplayIndex index;
    int scenario;
    ScenarioInfo Info => index.scenarios[scenario];
    ReplayPane[] panes;
    string loadError;

    float time;
    bool playing;
    float speed = 3f;
    bool showHeat, showOrders = true;
    bool menuOpen, helpOpen;

    // iki haritanın ortak görünümü (harita koordinatında merkez ve yakınlık)
    Vector2 viewCenter;
    float viewSize, fitSize;
    int dragPane = -1;
    Vector2 pressPos, lastMouse;

    GUIStyle bar, title, text, small, big, button, card, overlay;
    Texture2D track, warmTex, eventTex;

    void Start()
    {
        var art = new ReplayPane.Art
        {
            square = SpriteUtil.Square(), circle = SpriteUtil.Circle(), hollow = SpriteUtil.Ring(64, 0.38f),
            ring = SpriteUtil.Ring(), arrow = SpriteUtil.Arrow(), cross = SpriteUtil.Cross(),
            material = SpriteUtil.UnlitMaterial(),
        };
        var second = new GameObject("Camera 2").AddComponent<Camera>();
        panes = new[] { new ReplayPane(Camera.main, 0f, art), new ReplayPane(second, 10000f, art) };

        string file = Path.Combine(Application.streamingAssetsPath, replayFolder, "index.json");
        if (!File.Exists(file))
        {
            loadError = "replays/index.json yok. Önce: uv run python tools/export_replay.py";
            return;
        }
        index = JsonUtility.FromJson<ReplayIndex>(File.ReadAllText(file));
        panes[0].policy = 0;                          // solda en basit politika
        panes[1].policy = index.policies.Length - 1;  // sağda en gelişmiş politika
        ShowScenario(0);
    }

    ReplayRun Load(int policy)
    {
        string name = $"{Info.id}_{index.policies[policy].id}.json";
        return JsonUtility.FromJson<ReplayRun>(File.ReadAllText(Path.Combine(Application.streamingAssetsPath, replayFolder, name)));
    }

    void ShowScenario(int s)
    {
        scenario = s;
        time = 0f;
        playing = false;
        foreach (var p in panes)
        {
            p.selected = -1;
            p.Show(Load(p.policy), p.policy);
        }
        Fit();
        Redraw();
    }

    void SetPolicy(int pane, int policy)
    {
        policy = (policy + index.policies.Length) % index.policies.Length;
        panes[pane].Show(Load(policy), policy);
        Redraw();
    }

    // kamera

    void Layout()
    {
        float bottom = (BottomBar + PaneFooter) / RefHeight;
        float height = 1f - (TopBar + PaneHeader + BottomBar + PaneFooter) / RefHeight;
        float gap = Gap / RefHeight * Screen.height / Screen.width / 2f;
        panes[0].cam.rect = new Rect(0f, bottom, 0.5f - gap, height);
        panes[1].cam.rect = new Rect(0.5f + gap, bottom, 0.5f - gap, height);
    }

    void Fit()
    {
        Layout();
        var run = panes[0].run;
        float aspect = panes[0].cam.aspect;
        fitSize = Mathf.Max((run.height + 1f) / 2f, (run.width + 1f) / (2f * aspect));
        viewSize = fitSize;
        viewCenter = new Vector2((run.width - 1) / 2f, -(run.height - 1) / 2f);
        ApplyView();
    }

    void ApplyView()
    {
        foreach (var p in panes)
        {
            p.cam.orthographicSize = viewSize;
            p.cam.transform.position = new Vector3(viewCenter.x + p.offset, viewCenter.y, -10f);
        }
    }

    int PaneAt(Vector2 screen)
    {
        for (int i = 0; i < panes.Length; i++)
            if (panes[i].cam.pixelRect.Contains(screen)) return i;
        return -1;
    }

    void HandleMouse()
    {
        var mouse = Mouse.current;
        if (mouse == null || menuOpen || helpOpen) return;
        Vector2 pos = mouse.position.ReadValue();
        int over = PaneAt(pos);

        float scroll = mouse.scroll.ReadValue().y;
        if (over >= 0 && Mathf.Abs(scroll) > 0.01f)
        {
            var cam = panes[over].cam;
            Vector3 before = cam.ScreenToWorldPoint(pos);
            viewSize = Mathf.Clamp(viewSize * (scroll > 0 ? 0.88f : 1f / 0.88f), 3f, fitSize * 1.5f);
            ApplyView();
            Vector3 after = cam.ScreenToWorldPoint(pos);
            viewCenter += (Vector2)(before - after);   // imlecin altındaki nokta yerinde kalsın
            ApplyView();
        }

        if (mouse.leftButton.wasPressedThisFrame && over >= 0) { dragPane = over; pressPos = lastMouse = pos; }
        if (dragPane >= 0 && mouse.leftButton.isPressed)
        {
            var cam = panes[dragPane].cam;
            viewCenter += (Vector2)(cam.ScreenToWorldPoint(lastMouse) - cam.ScreenToWorldPoint(pos));
            ApplyView();
            lastMouse = pos;
        }
        if (dragPane >= 0 && mouse.leftButton.wasReleasedThisFrame)
        {
            var p = panes[dragPane];
            if ((pos - pressPos).magnitude < 6f) { p.selected = p.RobotAt(p.cam.ScreenToWorldPoint(pos)); Redraw(); }
            dragPane = -1;
        }
    }

    // oynatma

    int LastFrame => panes[0].run.frames.Length - 1;
    int Step => Mathf.Clamp(Mathf.FloorToInt(time), 0, LastFrame);

    void Update()
    {
        if (index == null) return;
        Layout();
        HandleMouse();

        var kb = Keyboard.current;
        if (kb != null)
        {
            if (kb.spaceKey.wasPressedThisFrame) TogglePlay();
            if (kb.rightArrowKey.wasPressedThisFrame) Seek(Mathf.Floor(time) + 1f);
            if (kb.leftArrowKey.wasPressedThisFrame) Seek(Mathf.Ceil(time) - 1f);
            if (kb.hKey.wasPressedThisFrame) { showHeat = !showHeat; Redraw(); }
            if (kb.escapeKey.wasPressedThisFrame)
            {
                menuOpen = helpOpen = false;
                foreach (var p in panes) p.selected = -1;
                Redraw();
            }
        }

        if (!playing) return;
        time += speed * Time.deltaTime;
        if (time >= LastFrame) { time = LastFrame; playing = false; }
        Redraw();
    }

    void TogglePlay()
    {
        if (time >= LastFrame) time = 0f;
        playing = !playing;
    }

    void Seek(float t)
    {
        time = Mathf.Clamp(t, 0f, LastFrame);
        Redraw();
    }

    void Redraw()
    {
        foreach (var p in panes) p.Apply(time, showOrders, showHeat);
    }

    // arayüz

    // Proje doğrusal renk uzayında, IMGUI ise dokuyu bir kez daha çeviriyor.
    // Renk önce doğrusala çevrilir ki ekranda yazıldığı gibi görünsün.
    static Texture2D Solid(Color c)
    {
        var t = new Texture2D(1, 1);
        var lin = c.linear;
        t.SetPixel(0, 0, new Color(lin.r, lin.g, lin.b, c.a));
        t.Apply();
        return t;
    }

    static string Hex(Color c) => ColorUtility.ToHtmlStringRGB(c);

    void Styles()
    {
        if (bar != null) return;
        bar = new GUIStyle { normal = { background = Solid(new Color(0.04f, 0.045f, 0.06f)) } };
        card = new GUIStyle { normal = { background = Solid(new Color(0.06f, 0.07f, 0.09f)) }, padding = new RectOffset(14, 14, 10, 10) };
        overlay = new GUIStyle { normal = { background = Solid(new Color(0f, 0f, 0f, 0.6f)) } };
        title = new GUIStyle { fontSize = 18, fontStyle = FontStyle.Bold, richText = true, normal = { textColor = Color.white } };
        text = new GUIStyle { fontSize = 14, richText = true, wordWrap = true, normal = { textColor = new Color(0.80f, 0.83f, 0.88f) } };
        small = new GUIStyle(text) { fontSize = 12, normal = { textColor = new Color(0.58f, 0.62f, 0.67f) } };
        big = new GUIStyle(title) { fontSize = 30 };
        button = new GUIStyle(GUI.skin.button) { fontSize = 14, richText = true };
        track = Solid(new Color(0.22f, 0.24f, 0.28f));
        warmTex = Solid(new Color(0.95f, 0.79f, 0.30f, 0.45f));
        eventTex = Solid(new Color(0.85f, 0.18f, 0.22f, 0.6f));
    }

    void OnGUI()
    {
        Styles();
        float k = Screen.height / RefHeight;
        GUI.matrix = Matrix4x4.Scale(new Vector3(k, k, 1f));
        float w = Screen.width / k, h = RefHeight;

        if (loadError != null) { GUI.Label(new Rect(20, 20, 900, 40), loadError, title); return; }

        GUI.enabled = !menuOpen && !helpOpen;
        // iki kameranın arasındaki şerit hiçbir kamerayla temizlenmiyor, üstü kapatılır
        GUI.DrawTexture(new Rect((w - Gap) / 2f, 0, Gap, h), bar.normal.background);
        DrawTop(w);
        for (int i = 0; i < panes.Length; i++) DrawPane(i, w, h);
        DrawBottom(w, h);
        GUI.enabled = true;

        if (menuOpen) DrawMenu(w, h);
        if (helpOpen) DrawHelp(w, h);
    }

    void DrawTop(float w)
    {
        GUI.Box(new Rect(0, 0, w, TopBar), GUIContent.none, bar);
        if (GUI.Button(new Rect(14, 10, 230, 32), $"<b>{Info.title}</b>  ▾", button)) menuOpen = true;
        GUI.Label(new Rect(258, 16, w - 420, 24), Info.about, text);

        string evt = ActiveEvent();
        if (evt != null) GUI.Label(new Rect(w - 420, 16, 340, 24), $"<color=#ff6b6b><b>{evt}</b></color>", text);
        if (GUI.Button(new Rect(w - 54, 10, 40, 32), "?", button)) helpOpen = true;
    }

    string ActiveEvent()
    {
        foreach (var e in Info.events)
        {
            if (Step < e.start || Step >= e.start + e.duration) continue;
            int left = e.start + e.duration - Step;
            return e.kind == "block" ? $"Koridor kapalı, {left} adım kaldı" : $"5 robot arızalı, {left} adım kaldı";
        }
        return null;
    }

    void DrawPane(int i, float w, float h)
    {
        var pane = panes[i];
        float half = (w - Gap) / 2f;
        float x = i == 0 ? 0f : half + Gap;
        int p = pane.policy;

        // üstte politika adı ve değiştirme okları
        GUI.Box(new Rect(x, TopBar, half, PaneHeader), GUIContent.none, bar);
        if (GUI.Button(new Rect(x + 10, TopBar + 6, 30, 28), "◀", button)) SetPolicy(i, p - 1);
        GUI.Label(new Rect(x + 50, TopBar + 9, half - 100, 26),
            $"<color=#{Hex(PolicyColors[p])}>●</color> <b>{index.policies[p].id}</b>  {index.policies[p].name}", title);
        if (GUI.Button(new Rect(x + half - 40, TopBar + 6, 30, 28), "▶", button)) SetPolicy(i, p + 1);

        // altta iki büyük sayı
        float y = h - BottomBar - PaneFooter;
        GUI.Box(new Rect(x, y, half, PaneFooter), GUIContent.none, bar);
        var s = Info.series[p];
        int step = Step;
        if (step < Info.warmup)
        {
            GUI.Label(new Rect(x + 20, y + 22, half - 40, 30),
                $"Isınma: ölçüm {Info.warmup}. adımda başlar", text);
        }
        else
        {
            GUI.Label(new Rect(x + 20, y + 8, 160, 40), s.completed[step].ToString(), big);
            GUI.Label(new Rect(x + 20, y + 46, 200, 20), "sipariş teslim edildi", small);
            string mean = s.completed[step] > 0 ? s.meanTime[step].ToString("0") : "–";
            GUI.Label(new Rect(x + 210, y + 8, 160, 40), mean, big);
            GUI.Label(new Rect(x + 210, y + 46, 220, 20), "adımda teslim (ortalama)", small);
            if (s.stuck[step] > 0)
                GUI.Label(new Rect(x + half - 170, y + 26, 160, 24), $"<color=#ff6b6b>{s.stuck[step]} robot sıkışık</color>", text);
        }

        if (pane.selected >= 0) DrawCard(pane, x);
    }

    void DrawCard(ReplayPane pane, float x)
    {
        var fr = pane.run.frames[Step];
        int r = pane.selected;
        bool broken = System.Array.IndexOf(fr.failed, r) >= 0;
        string state = broken ? "arızalı"
                     : fr.phase[r] == 0 ? "parkta bekliyor"
                     : fr.blocked[r] > 0 ? $"<color=#ff6b6b>{fr.blocked[r]} adımdır ilerleyemiyor</color>"
                     : PhaseNames[fr.phase[r]];
        int left = fr.plan[r] >= 0 ? pane.run.plans[fr.plan[r]].xs.Length - fr.planOffset[r] : 0;
        string order = fr.order[r] >= 0 ? $"Sipariş #{fr.order[r]}, hedefe {left} adım" : "Siparişi yok";

        GUILayout.BeginArea(new Rect(x + 10, TopBar + PaneHeader + 10, 250, 88), card);
        GUILayout.Label($"Robot {r}", title);
        GUILayout.Label(state, text);
        GUILayout.Label(order, small);
        GUILayout.EndArea();
    }

    void DrawBottom(float w, float h)
    {
        float y = h - BottomBar;
        GUI.Box(new Rect(0, y, w, BottomBar), GUIContent.none, bar);
        if (GUI.Button(new Rect(14, y + 12, 44, 32), playing ? "❚❚" : "▶", button)) TogglePlay();

        for (int i = 0; i < Speeds.Length; i++)
        {
            bool on = Mathf.Approximately(speed, Speeds[i]);
            if (GUI.Button(new Rect(66 + i * 44, y + 12, 40, 32), on ? $"<b>{Speeds[i]}×</b>" : $"{Speeds[i]}×", button))
                speed = Speeds[i];
        }

        float bx = 256, bw = w - bx - 250;
        var slider = new Rect(bx, y + 20, bw, 16);
        GUI.DrawTexture(new Rect(bx, y + 25, bw, 6), track);
        GUI.DrawTexture(new Rect(bx, y + 25, bw * Info.warmup / LastFrame, 6), warmTex);
        foreach (var e in Info.events)
            GUI.DrawTexture(new Rect(bx + bw * e.start / LastFrame, y + 25, bw * e.duration / LastFrame, 6), eventTex);
        float t = GUI.HorizontalSlider(slider, time, 0f, LastFrame);
        if (!Mathf.Approximately(t, time)) Seek(t);

        GUI.Label(new Rect(w - 236, y + 18, 100, 24), $"Adım <b>{Step}</b>", text);
        bool heat = GUI.Toggle(new Rect(w - 136, y + 18, 130, 24), showHeat, " Isı haritası");
        if (heat != showHeat) { showHeat = heat; Redraw(); }
    }

    // Ekranı karartır. Kartın dışına tıklanırsa true döner.
    bool Dim(float w, float h)
    {
        GUI.DrawTexture(new Rect(0, 0, w, h), overlay.normal.background);
        return GUI.Button(new Rect(0, 0, w, h), GUIContent.none, GUIStyle.none);
    }

    void DrawMenu(float w, float h)
    {
        if (Dim(w, h)) { menuOpen = false; return; }
        GUILayout.BeginArea(new Rect(14, TopBar, 480, 64 * index.scenarios.Length + 20), card);
        for (int s = 0; s < index.scenarios.Length; s++)
        {
            var sc = index.scenarios[s];
            if (GUILayout.Button($"<b>{sc.title}</b>\n<size=12>{sc.about}</size>", button, GUILayout.Height(56)))
            {
                menuOpen = false;
                ShowScenario(s);
            }
        }
        GUILayout.EndArea();
    }

    void DrawHelp(float w, float h)
    {
        if (Dim(w, h)) { helpOpen = false; return; }
        GUILayout.BeginArea(new Rect(w / 2 - 330, 90, 660, 350), card);
        GUILayout.Label("Ne görüyorum?", title);
        GUILayout.Space(6);
        GUILayout.Label("İki harita aynı siparişleri farklı yöntemlerle karşılar. Haritaların üstündeki oklarla yöntem değişir.", text);
        GUILayout.Space(8);
        foreach (var p in index.policies)
        {
            GUILayout.Label($"<b>{p.id} · {p.name}</b>: {p.about}", text);
            GUILayout.Space(3);
        }
        GUILayout.Space(10);
        GUILayout.Label(
            Dot("●", ReplayPane.Moving, "ürün taşıyan robot") + Dot("○", ReplayPane.Moving, "boş robot")
            + Dot("●", ReplayPane.Stuck, "ilerleyemeyen robot") + Dot("✕", ReplayPane.Failed, "arızalı robot") + "\n"
            + Dot("◆", ReplayPane.OrderColor, "kimseye verilmemiş sipariş") + Dot("■", ReplayPane.Closed, "kapalı koridor") + "\n"
            + Dot("■", ReplayPane.Shelf, "raf") + Dot("■", ReplayPane.Station, "paketleme masası") + Dot("■", ReplayPane.ParkMark, "park yeri"),
            text);
        GUILayout.Space(10);
        GUILayout.Label("İlk 200 adım ısınmadır, sayılara katılmaz. Isı haritası son 100 adımda robotların en çok beklediği yerleri boyar.", text);
        GUILayout.Space(10);
        GUILayout.Label("Boşluk: oynat / duraklat · ← →: tek adım · tekerlek: yakınlaştır · sürükle: kaydır · robota tıkla: rotası · H: ısı haritası · Esc: kapat", small);
        GUILayout.EndArea();
    }

    static string Dot(string symbol, Color c, string label) => $"<color=#{Hex(c)}>{symbol}</color> {label}     ";
}
