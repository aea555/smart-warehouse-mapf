using System;
using System.Collections.Generic;
using UnityEngine;

// Ekrandaki iki haritadan biri. Her haritanın kendi kamerası, kaydı ve robotları var.
// İki harita üst üste binmesin diye her biri dünyada farklı bir x konumuna kurulur.
public class ReplayPane
{
    public static readonly Color Background = new Color(0.07f, 0.08f, 0.10f);
    static readonly Color Floor      = new Color(0.17f, 0.19f, 0.23f);
    static readonly Color Wall       = new Color(0.11f, 0.12f, 0.15f);
    public static readonly Color Shelf   = new Color(0.72f, 0.47f, 0.22f);
    public static readonly Color Station = new Color(0.20f, 0.65f, 0.60f);
    static readonly Color DropMark   = new Color(0.17f, 0.36f, 0.37f);
    public static readonly Color ParkMark = new Color(0.24f, 0.27f, 0.32f);
    public static readonly Color OrderColor = new Color(0.98f, 0.80f, 0.25f);
    public static readonly Color Moving  = new Color(0.36f, 0.66f, 1.00f);
    public static readonly Color Stuck   = new Color(1.00f, 0.30f, 0.30f);
    public static readonly Color Failed  = new Color(0.55f, 0.57f, 0.60f);
    public static readonly Color Closed  = new Color(0.85f, 0.18f, 0.22f, 0.9f);

    const int MapPx = 8;          // harita dokusunda hücre başına piksel
    const int HeatWindow = 100;   // ısı haritası son kaç adıma bakar
    const float HeatCap = 40f;    // bu kadar bekleme tam kırmızı
    const float DimAlpha = 0.25f;

    public readonly Camera cam;
    public readonly float offset;
    public ReplayRun run;
    public int policy;
    public int selected = -1;

    readonly Art art;
    Transform world;
    SpriteRenderer[] robots = new SpriteRenderer[0], arrows, crosses;
    readonly List<SpriteRenderer> orders = new List<SpriteRenderer>();
    readonly List<SpriteRenderer> closed = new List<SpriteRenderer>();
    Transform orderRoot, closedRoot;
    LineRenderer route;
    SpriteRenderer selectRing, targetMark;

    Texture2D heatTex;
    SpriteRenderer heatSprite;
    Color32[] heatPixels;
    int[] heatCounts;
    int heatFrame = -1;

    // iki haritanın ortak kullandığı şekiller
    public class Art
    {
        public Sprite square, circle, hollow, ring, arrow, cross;
        public Material material;
    }

    public ReplayPane(Camera cam, float offset, Art art)
    {
        this.cam = cam;
        this.offset = offset;
        this.art = art;
        cam.orthographic = true;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Background;
    }

    Vector3 World(float x, float y) => new Vector3(x + offset, -y, 0f);

    public Vector3 Center => World((run.width - 1) / 2f, (run.height - 1) / 2f);

    public void Show(ReplayRun newRun, int newPolicy)
    {
        run = newRun;
        policy = newPolicy;
        if (world != null) UnityEngine.Object.Destroy(world.gameObject);
        world = new GameObject($"World {offset}").transform;
        if (selected >= run.robots) selected = -1;
        heatFrame = -1;

        BuildMap();
        closedRoot = Group("Closed");
        orderRoot = Group("Orders");
        closed.Clear();
        orders.Clear();

        var robotRoot = Group("Robots");
        int n = run.robots;
        robots = new SpriteRenderer[n];
        arrows = new SpriteRenderer[n];
        crosses = new SpriteRenderer[n];
        for (int i = 0; i < n; i++)
        {
            robots[i] = Spawn($"Robot {i}", art.circle, Vector3.zero, Moving, 0.72f, 5, robotRoot);
            arrows[i] = Child(robots[i], art.arrow, Color.white, 0.45f, 7);
            crosses[i] = Child(robots[i], art.cross, new Color(0.12f, 0.12f, 0.14f), 0.8f, 6);
        }

        var lineGo = new GameObject("Route");
        lineGo.transform.SetParent(world, false);
        route = lineGo.AddComponent<LineRenderer>();
        route.sharedMaterial = art.material;
        route.startWidth = route.endWidth = 0.14f;
        route.startColor = route.endColor = Color.white;
        route.sortingOrder = 4;
        route.numCornerVertices = 2;
        route.positionCount = 0;
        selectRing = Spawn("SelectRing", art.ring, Vector3.zero, Color.white, 1.25f, 8, world);
        targetMark = Spawn("Target", art.ring, Vector3.zero, Color.white, 0.9f, 8, world);
        selectRing.enabled = targetMark.enabled = false;
    }

    Transform Group(string name)
    {
        var t = new GameObject(name).transform;
        t.SetParent(world, false);
        return t;
    }

    SpriteRenderer Spawn(string name, Sprite sprite, Vector3 pos, Color color, float scale, int order, Transform parent)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        go.transform.position = pos;
        go.transform.localScale = new Vector3(scale, scale, 1f);
        var sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = sprite;
        sr.color = color;
        sr.sortingOrder = order;
        if (art.material != null) sr.sharedMaterial = art.material;
        return sr;
    }

    SpriteRenderer Child(SpriteRenderer parent, Sprite sprite, Color color, float scale, int order)
    {
        var sr = Spawn("Child", sprite, Vector3.zero, color, scale, order, parent.transform);
        sr.transform.localPosition = Vector3.zero;
        return sr;
    }

    // Sabit harita tek bir doku olarak çizilir. Büyük depoda binlerce nesne yerine tek sprite yeterli.
    void BuildMap()
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
        Color32 shelf = Shelf, wall = Wall, gap = Background;
        for (int py = 0; py < h * MapPx; py++)
        for (int pxX = 0; pxX < w * MapPx; pxX++)
        {
            Color32 c = colors[pxX / MapPx + (h - 1 - py / MapPx) * w];   // doku alttan başlar
            bool edge = pxX % MapPx == 0 || py % MapPx == 0;
            bool solid = c.Equals(shelf) || c.Equals(wall);                 // raflar bitişik görünsün
            px[pxX + py * w * MapPx] = edge && !solid ? gap : c;
        }
        tex.SetPixels32(px);
        tex.Apply();
        Spawn("Map", Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f), MapPx),
              Center, Color.white, 1f, 0, world);

        heatTex = SpriteUtil.CellTexture(w, h);
        heatPixels = new Color32[w * h];
        heatCounts = new int[w * h];
        heatTex.SetPixels32(heatPixels);
        heatTex.Apply();
        heatSprite = Spawn("Heat", Sprite.Create(heatTex, new Rect(0, 0, w, h), new Vector2(0.5f, 0.5f), 1f),
                           Center, Color.white, 1f, 2, world);
    }

    // time kesirli bir adım. İki adım arası yumuşak geçişle çizilir.
    public void Apply(float time, bool showOrders, bool showHeat)
    {
        int last = run.frames.Length - 1;
        int i = Mathf.Clamp(Mathf.FloorToInt(time), 0, last);
        int j = Mathf.Min(i + 1, last);
        float f = Mathf.SmoothStep(0f, 1f, time - i);
        var a = run.frames[i];
        var b = run.frames[j];
        bool focus = selected >= 0;

        for (int r = 0; r < robots.Length; r++)
        {
            robots[r].transform.position = World(Mathf.Lerp(a.xs[r], b.xs[r], f), Mathf.Lerp(a.ys[r], b.ys[r], f));

            // dolu daire ürün taşıyor, boş daire taşımıyor, kırmızı ilerleyemiyor, gri çarpılı arızalı
            bool broken = Array.IndexOf(a.failed, r) >= 0;
            robots[r].sprite = a.phase[r] == 2 || broken ? art.circle : art.hollow;
            Color c = broken ? Failed : a.blocked[r] > 0 ? Stuck : Moving;
            if (focus && r != selected) c.a = DimAlpha;
            robots[r].color = c;
            crosses[r].enabled = broken;

            int dx = a.nx[r] - a.xs[r], dy = a.ny[r] - a.ys[r];
            bool show = r == selected && (dx != 0 || dy != 0);
            arrows[r].enabled = show;
            if (show)
            {
                arrows[r].transform.localPosition = new Vector3(dx, -dy, 0f) * 0.62f;
                arrows[r].transform.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(-dy, dx) * Mathf.Rad2Deg);
            }
        }

        Marks(orders, orderRoot, showOrders ? a.openPicks : new CellXY[0], OrderColor, 0.30f, 3, 45f, focus ? DimAlpha : 1f);
        Marks(closed, closedRoot, a.closed ?? new CellXY[0], Closed, 0.92f, 1, 0f, 1f);

        heatSprite.enabled = showHeat;
        if (showHeat && heatFrame != i) UpdateHeat(i);

        selectRing.enabled = targetMark.enabled = focus;
        if (!focus) { route.positionCount = 0; return; }
        Vector3 here = robots[selected].transform.position;
        selectRing.transform.position = here;
        targetMark.transform.position = World(a.tx[selected], a.ty[selected]);
        var pts = new List<Vector3> { here };
        if (a.plan[selected] >= 0)
        {
            var plan = run.plans[a.plan[selected]];
            for (int k = a.planOffset[selected]; k < plan.xs.Length; k++) pts.Add(World(plan.xs[k], plan.ys[k]));
        }
        route.positionCount = pts.Count;
        route.SetPositions(pts.ToArray());
    }

    void Marks(List<SpriteRenderer> pool, Transform root, CellXY[] cells, Color color,
               float scale, int order, float angle, float alpha)
    {
        while (pool.Count < cells.Length)
        {
            var d = Spawn("Mark", art.square, Vector3.zero, color, scale, order, root);
            d.transform.rotation = Quaternion.Euler(0f, 0f, angle);
            pool.Add(d);
        }
        for (int k = 0; k < pool.Count; k++)
        {
            pool[k].enabled = k < cells.Length;
            if (k >= cells.Length) continue;
            pool[k].transform.position = World(cells[k].x, cells[k].y);
            pool[k].color = new Color(color.r, color.g, color.b, color.a * alpha);
        }
    }

    // Son 100 adımda görevdeki bir robot yerinden kımıldamadıysa, durduğu hücreye bir puan yazılır.
    // Puan arttıkça hücre sarıdan kırmızıya döner.
    void UpdateHeat(int i)
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
            int p = x + (h - 1 - y) * w;
            if (n == 0) { heatPixels[p] = new Color32(0, 0, 0, 0); continue; }
            float v = Mathf.Clamp01(n / HeatCap);
            Color c = Color.Lerp(low, high, v);
            c.a = 0.35f + 0.55f * v;
            heatPixels[p] = c;
        }
        heatTex.SetPixels32(heatPixels);
        heatTex.Apply();
    }

    public int RobotAt(Vector3 p)
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

    public Vector3 RobotPosition(int r) => robots[r].transform.position;
}
