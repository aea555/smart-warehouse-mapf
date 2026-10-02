using System;

// tools/export_scene.py'nin yazdığı scene.json için sınıflar.
// JsonUtility iç içe dizi okuyamıyor, o yüzden hücreler {x, y} nesnesi.

[Serializable]
public class CellXY
{
    public int x;
    public int y;
}

[Serializable]
public class Scenario
{
    public int seed;
    public int width;
    public int height;
    public CellXY[] shelves;
    public CellXY[] obstacles;
    public CellXY start;
    public CellXY goal;
    public CellXY[] path;
}

[Serializable]
public class ScenarioSet
{
    public Scenario[] scenarios;
}
