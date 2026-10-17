using System;

// tools/export_replay.py'nin yazdığı replay.json için sınıflar.
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
    public string label;
    public string policy;
    public string density;
    public int robots;
    public float rate;
    public int seed;
    public int warmup;       // bu adıma kadar ölçüm yok
    public int width;
    public int height;
    public CellXY[] shelves;
    public CellXY[] stations;
    public CellXY[] drops;
    public CellXY[] parks;
    public int ordersArrived;
    public ReplayOrder[] orders;
    public ReplayPlan[] plans;
    public ReplayFrame[] frames;
}

[Serializable]
public class ReplaySet
{
    public ReplayRun[] runs;
}
