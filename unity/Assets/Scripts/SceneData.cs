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
public class SceneData
{
    public int width;
    public int height;
    public CellXY[] blocked;
    public CellXY start;
    public CellXY goal;
    public bool hasPath;
    public CellXY[] path;
}
