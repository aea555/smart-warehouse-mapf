using System;

// tools/export_replay.py'nin yazdığı replays/*.json dosyaları için sınıflar.
// JsonUtility iç içe dizi okuyamıyor, o yüzden konumlar ayrı xs/ys dizileri.

[Serializable]
public class ReplayFrame
{
    public int[] xs;
    public int[] ys;
    public int[] nx;         // bir sonraki adımda gitmek istediği hücre
    public int[] ny;
    public int[] tx;         // şu anki hedef (raf, masa ya da park)
    public int[] ty;
    public int[] plan;       // ReplayRun.plans içindeki plan, yoksa -1
    public int[] planOffset; // planın kaçıncı hücresinde
    public int[] order;      // ilgili sipariş, yoksa -1
    public int[] phase;      // 0 boşta, 1 toplamaya gidiyor, 2 teslimata gidiyor, 3 parka dönüyor
    public int[] blocked;    // art arda ilerleyemediği adım sayısı
    public int[] failed;     // bu adımda arızalı robotlar
    public CellXY[] closed;  // geçici kapalı hücreler (koridor kapanması)
    public CellXY[] openPicks;
    public int arrived;
    public int open;
    public int completed;
    public int conflicts;
}

[Serializable]
public class ReplayPlan
{
    public int[] xs;
    public int[] ys;
}

[Serializable]
public class ReplayOrder
{
    public int id;
    public int arrival;
    public CellXY pick;
    public CellXY drop;
}

[Serializable]
public class ReplayRun
{
    public string scenario;
    public string label;
    public string policyId;
    public string policy;
    public string density;
    public int robots;
    public float rate;
    public int seed;
    public int warmup;       // bu adıma kadar ölçüm yok
    public int width;
    public int height;
    public CellXY[] shelves;
    public CellXY[] walls;
    public CellXY[] stations;
    public CellXY[] drops;
    public CellXY[] parks;
    public int ordersArrived;
    public ReplayOrder[] orders;
    public ReplayPlan[] plans;
    public ReplayFrame[] frames;
}

// index.json'daki senaryolar ve politikaların adım adım metrikleri

[Serializable]
public class ReplayEvent
{
    public string kind;      // "block" ya da "fail"
    public int start;
    public int duration;
}

[Serializable]
public class PolicySeries
{
    public string policy;
    public int[] completed;  // ısınmadan sonra biten sipariş
    public float[] meanTime; // ortalama tamamlanma süresi
    public int[] open;       // bekleyen sipariş
    public int[] stuck;      // ilerleyemeyen robot
}

[Serializable]
public class ScenarioInfo
{
    public string id;
    public string title;
    public string about;
    public int robots;
    public float rate;
    public int seed;
    public int warmup;
    public ReplayEvent[] events;
    public PolicySeries[] series;
}

[Serializable]
public class PolicyInfo
{
    public string id;
    public string name;
    public string about;
}

[Serializable]
public class ReplayIndex
{
    public PolicyInfo[] policies;
    public ScenarioInfo[] scenarios;
}
