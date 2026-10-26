"""Trendyol satıcı API'sinden ürünleri çeker ve ana ürün bazında gruplar."""
import base64
import os
import time

import requests

API = "https://apigw.trendyol.com/integration/product/sellers/{sid}/products"


def _oturum():
    sid = os.environ["TRENDYOL_SELLER_ID"].strip()
    key = os.environ["TRENDYOL_API_KEY"].strip()
    sec = os.environ["TRENDYOL_API_SECRET"].strip()
    s = requests.Session()
    s.headers.update({
        "Authorization": "Basic " + base64.b64encode(f"{key}:{sec}".encode()).decode(),
        "User-Agent": f"{sid} - SelfIntegration",
        "Accept": "application/json",
    })
    return s, sid


def tum_varyantlar():
    """Onaylı ve satıştaki tüm varyantları döndürür."""
    s, sid = _oturum()
    url = API.format(sid=sid)
    sonuc, sayfa = [], 0
    while True:
        for deneme in range(4):
            r = s.get(url, params={"approved": "true", "archived": "false",
                                   "page": sayfa, "size": 100}, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * (deneme + 1))
                continue
            break
        r.raise_for_status()
        veri = r.json()
        sonuc.extend(veri.get("content", []))
        sayfa += 1
        if sayfa >= int(veri.get("totalPages", 1) or 1):
            break
        time.sleep(0.3)
    return sonuc


def _link(v):
    if v.get("productUrl"):
        return v["productUrl"]
    pcid = v.get("productContentId")
    if pcid:
        return f"https://www.trendyol.com/morro/urun-p-{pcid}"
    return None


def _marka(v):
    b = v.get("brand") or v.get("brandName") or ""
    if isinstance(b, dict):
        b = b.get("name") or ""
    return str(b).strip()


# Gönderi açıklamasında gösterilecek ürün özellikleri (Trendyol özellik adları)
OZELLIKLER = ["Materyal Bileşeni", "Materyal", "Kumaş Tipi", "Paket İçeriği", "Kalıp",
              "Bel", "Yaka Tipi", "Kol Boyu", "Paça Tipi", "Desen", "Ek Özellik", "Ürün Detayı"]


def urunler():
    """Varyantları ana ürüne (productMainId) göre birleştirir.

    Dönen her ürün: id, baslik, kategori, fiyat (en düşük satış),
    liste_fiyat, stok (toplam), gorseller, link
    """
    gruplar = {}
    for v in tum_varyantlar():
        if v.get("archived") or v.get("locked") or v.get("rejected"):
            continue
        if v.get("onSale") is False:
            continue
        anahtar = str(v.get("productMainId") or v.get("title") or v.get("barcode"))
        g = gruplar.setdefault(anahtar, {
            "id": anahtar,
            "baslik": (v.get("title") or "").strip(),
            "kategori": v.get("categoryName") or v.get("pimCategoryId") or "",
            "marka": _marka(v),
            "fiyat": None,
            "liste_fiyat": None,
            "stok": 0,
            "stoklu_beden": [],
            "renkler": [],
            "ozellikler": {},
            "gorseller": [],
            "link": None,
        })
        adet = int(v.get("quantity") or 0)
        g["stok"] += adet
        oz = {str(a.get("attributeName", "")).strip(): str(a.get("attributeValue") or "").strip()
              for a in v.get("attributes", []) or [] if a.get("attributeValue")}
        for ad in OZELLIKLER:
            if oz.get(ad) and ad not in g["ozellikler"]:
                g["ozellikler"][ad] = oz[ad]
        renk = (v.get("color") or oz.get("Renk") or "").strip()
        if adet > 0 and renk and renk not in g["renkler"]:
            g["renkler"].append(renk)
        satis = float(v.get("salePrice") or 0)
        liste = float(v.get("listPrice") or 0)
        if adet > 0 and satis > 0:
            if g["fiyat"] is None or satis < g["fiyat"]:
                g["fiyat"] = satis
                g["liste_fiyat"] = max(liste, satis)
            beden = next((a.get("attributeValue") for a in v.get("attributes", [])
                          if str(a.get("attributeName", "")).lower() in ("beden", "size")), None)
            if beden and beden not in g["stoklu_beden"]:
                g["stoklu_beden"].append(beden)
        for img in v.get("images", []) or []:
            u = img.get("url") if isinstance(img, dict) else img
            if u and u not in g["gorseller"]:
                g["gorseller"].append(u)
        g["link"] = g["link"] or _link(v)
    return [g for g in gruplar.values() if g["fiyat"]]
