using UnityEngine;

// Basit şekilleri kodda üretiyoruz, asset dosyasına gerek kalmasın.
public static class SpriteUtil
{
    public static Sprite Square()
    {
        var tex = new Texture2D(4, 4) { filterMode = FilterMode.Point };
        var px = new Color[16];
        for (int i = 0; i < px.Length; i++) px[i] = Color.white;
        tex.SetPixels(px);
        tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, 4, 4), new Vector2(0.5f, 0.5f), 4f);
    }

    public static Sprite Circle(int res = 64)
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

    // içi boş halka, thickness yarıçapa oran
    public static Sprite Ring(int res = 64, float thickness = 0.18f)
    {
        var tex = new Texture2D(res, res) { filterMode = FilterMode.Bilinear };
        float r = res / 2f, inner = r * (1f - thickness);
        for (int y = 0; y < res; y++)
        for (int x = 0; x < res; x++)
        {
            float d = Vector2.Distance(new Vector2(x + 0.5f, y + 0.5f), new Vector2(r, r));
            float a = Mathf.Clamp01(r - d) * Mathf.Clamp01(d - inner);
            tex.SetPixel(x, y, new Color(1f, 1f, 1f, a));
        }
        tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, res, res), new Vector2(0.5f, 0.5f), res);
    }

    // sağa bakan üçgen ok
    public static Sprite Arrow(int res = 64)
    {
        var tex = new Texture2D(res, res) { filterMode = FilterMode.Bilinear };
        for (int y = 0; y < res; y++)
        for (int x = 0; x < res; x++)
        {
            float u = (x + 0.5f) / res, v = Mathf.Abs((y + 0.5f) / res - 0.5f) * 2f;
            float a = Mathf.Clamp01((1f - u - v) * res * 0.5f);   // kenarlarda yumuşatma
            tex.SetPixel(x, y, new Color(1f, 1f, 1f, a));
        }
        tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, res, res), new Vector2(0.5f, 0.5f), res);
    }

    public static Material UnlitMaterial()
    {
        var unlit = Shader.Find("Universal Render Pipeline/2D/Sprite-Unlit-Default");
        return unlit != null ? new Material(unlit) : null;
    }
}
