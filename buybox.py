"""Trendyol buybox fiyat takibi (Morro Tekstil).

Kural: fiyatımız rakibin %1 altında durur.
  - Hiçbir zaman TABANIN altına inmez (maliyet + kargo + komisyon + kâr kuralı).
  - Hiçbir zaman TAVANIN üstüne çıkmaz (DLAP'taki fiyat; geçerse DLAP geri düzeltir).
  - Rakip fiyat yükseltirse biz de yükseliriz; fiyat tabanın altında kalmışsa tabana çekeriz.
  - Fiyatımız buybox fiyatından düşük olduğu halde buybox rakipteyse ek indirim yapılmaz.

Takip edilecek ürünler buybox/urunler.csv dosyasındadır (sadece bu dosyadaki barkodlara dokunulur):
  barkod, ad, maliyet, tavan, kural, aktif
  kural: "normal"  -> maliyet +%10 kâr
         "kis300"  -> en az 300 TL net kâr (U.S. Polo kışlık), %10'dan düşükse %10
         "basabas" -> zarar etmesin yeter (kısa kollular, Pierre Cardin sütyen takımları)
  aktif: 1 = takip et, 0 = dokunma (flaş teklif, kampanya vb. için geçici kapatma)

Gizli bilgiler GitHub Secrets'tadır (TRENDYOL_SELLER_ID, TRENDYOL_API_KEY, TRENDYOL_API_SECRET).
DENEME=1 ile çalıştırılırsa hiçbir fiyatı değiştirmez, sadece ne yapacağını yazar.
"""
import csv
import json
import math
import os
import sys
import time
from datetime import datetime, timezone, timedelta

from trendyol import _oturum

# --- Maliyet hesabı (mevcut Trendyol kurallarıyla aynı) ---
KARGO = 98.34          # 81,95 TL + KDV, 3 desiye kadar
KOMISYON = 0.215       # %21,5
KAR_ORANI = 0.10       # normal kural: maliyet üzerinden %10
KIS_KAR_TL = 300.0     # kis300 kuralı: en az 300 TL net kâr
RAKIP_ALTI = 0.01      # rakibin %1 altı
MIN_DEGISIM = 0.50     # bundan küçük fiyat farkları için istek atılmaz (TL)

URUN_DOSYASI = os.path.join(os.path.dirname(__file__), "buybox", "urunler.csv")
KAYIT_KLASORU = os.path.join(os.path.dirname(__file__), "buybox", "kayit")
TR = timezone(timedelta(hours=3))

URUN_API = "https://apigw.trendyol.com/integration/product/sellers/{sid}/products"
BUYBOX_API = "https://apigw.trendyol.com/integration/product/sellers/{sid}/products/buybox-information"
FIYAT_API = "https://apigw.trendyol.com/integration/inventory/sellers/{sid}/products/price-and-inventory"
BATCH_API = "https://apigw.trendyol.com/integration/product/sellers/{sid}/products/batch-requests/{bid}"


def yukari(x):
    return math.ceil(x * 100 - 1e-9) / 100


def asagi(x):
    return math.floor(x * 100 + 1e-9) / 100


def taban_hesapla(maliyet, kural):
    bolen = 1 - KOMISYON
    normal = (maliyet * (1 + KAR_ORANI) + KARGO) / bolen
    if kural == "basabas":
        return yukari((maliyet + KARGO) / bolen)
    if kural == "kis300":
        return yukari(max(normal, (maliyet + KIS_KAR_TL + KARGO) / bolen))
    return yukari(normal)


def urunleri_oku():
    urunler = []
    with open(URUN_DOSYASI, encoding="utf-8") as f:
        for s in csv.DictReader(f):
            if str(s.get("aktif", "1")).strip() != "1":
                continue
            b = s["barkod"].strip()
            if not b:
                continue
            maliyet = float(s["maliyet"].replace(",", "."))
            tavan = float(s["tavan"].replace(",", "."))
            kural = s["kural"].strip().lower()
            if kural not in ("normal", "kis300", "basabas"):
                raise ValueError(f"{b}: bilinmeyen kural '{kural}'")
            urunler.append({"barkod": b, "ad": s.get("ad", "").strip(), "maliyet": maliyet,
                            "tavan": tavan, "kural": kural,
                            "taban": taban_hesapla(maliyet, kural)})
    return urunler


def _istek(s, yontem, url, **kw):
    for deneme in range(4):
        r = s.request(yontem, url, timeout=60, **kw)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (deneme + 1))
            continue
        return r
    return r


def guncel_fiyatlar(s, sid, barkodlar):
    """barkod -> {satis, liste, stok}"""
    sonuc = {}
    for b in barkodlar:
        r = _istek(s, "GET", URUN_API.format(sid=sid), params={"barcode": b, "approved": "true"})
        r.raise_for_status()
        for v in r.json().get("content", []):
            if v.get("barcode") == b:
                sonuc[b] = {"satis": float(v.get("salePrice") or 0),
                            "liste": float(v.get("listPrice") or 0),
                            "stok": int(v.get("quantity") or 0),
                            "satista": v.get("onSale") is not False}
        time.sleep(0.2)
    return sonuc


def buybox_bilgisi(s, sid, barkodlar):
    sonuc = {}
    for i in range(0, len(barkodlar), 10):
        parca = barkodlar[i:i + 10]
        r = _istek(s, "POST", BUYBOX_API.format(sid=sid), json={"barcodes": parca},
                   headers={"storeFrontCode": "TR"})
        r.raise_for_status()
        for x in r.json().get("buyboxInfo", []):
            sonuc[x["barcode"]] = x
        time.sleep(0.2)
    return sonuc


def hedef_fiyat(u, fiyat, bb):
    """(yeni_fiyat veya None, açıklama)"""
    simdiki = fiyat["satis"]
    sira = bb.get("buyboxOrder")
    bb_fiyat = float(bb.get("buyboxPrice") or 0)
    ikinci = float(bb.get("secondBuyboxPrice") or 0)
    coklu = bool(bb.get("hasMultipleSeller"))

    if not coklu:
        hedef, neden = u["tavan"], "rakip yok → tavan"
    elif sira == 1:
        if ikinci > 0:
            hedef, neden = ikinci * (1 - RAKIP_ALTI), f"buybox bizde, 2. satıcı {ikinci:.2f}"
        else:
            hedef, neden = u["tavan"], "buybox bizde, 2. fiyat yok → tavan"
    else:
        if simdiki <= bb_fiyat + 0.01:
            # Fiyat bizde ama buybox rakipte (puan/kargo hızı vb.) → ek indirim yok
            if simdiki < u["taban"] - 0.01:
                return u["taban"], f"buybox rakipte ({bb_fiyat:.2f}), fiyat tabanın altındaydı → tabana"
            return None, f"fiyat bizde ama buybox rakipte ({bb_fiyat:.2f}) → indirim yok"
        hedef, neden = bb_fiyat * (1 - RAKIP_ALTI), f"buybox rakipte {bb_fiyat:.2f}"

    hedef = asagi(hedef)
    if hedef < u["taban"]:
        hedef, neden = u["taban"], neden + " → taban"
    if hedef > u["tavan"]:
        hedef, neden = u["tavan"], neden + " → tavan"
    if abs(hedef - simdiki) < MIN_DEGISIM:
        return None, neden + " (değişiklik yok)"
    return hedef, neden


def kaydet(satirlar):
    os.makedirs(KAYIT_KLASORU, exist_ok=True)
    simdi = datetime.now(TR)
    yol = os.path.join(KAYIT_KLASORU, simdi.strftime("%Y-%m-%d") + ".csv")
    yeni = not os.path.exists(yol)
    with open(yol, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if yeni:
            w.writerow(["saat", "barkod", "ad", "eski", "yeni", "taban", "tavan", "neden", "sonuc"])
        for s in satirlar:
            w.writerow([simdi.strftime("%H:%M")] + s)


def main():
    deneme = os.environ.get("DENEME", "0") == "1"
    urunler = urunleri_oku()
    if not urunler:
        print("Takip edilecek ürün yok.")
        return 0
    s, sid = _oturum()
    barkodlar = [u["barkod"] for u in urunler]
    fiyatlar = guncel_fiyatlar(s, sid, barkodlar)
    bb = buybox_bilgisi(s, sid, barkodlar)

    degisecek, rapor, kayit = [], [], []
    for u in urunler:
        f, b = fiyatlar.get(u["barkod"]), bb.get(u["barkod"])
        if not f or not b:
            rapor.append(f"- {u['ad'] or u['barkod']}: Trendyol'da bulunamadı/buybox bilgisi yok, atlandı")
            continue
        if not f["satista"] or f["stok"] <= 0:
            rapor.append(f"- {u['ad'] or u['barkod']}: satışta değil/stok yok, atlandı")
            continue
        yeni, neden = hedef_fiyat(u, f, b)
        satir = f"- {u['ad'] or u['barkod']}: {f['satis']:.2f} TL (taban {u['taban']:.2f}, tavan {u['tavan']:.2f}) · {neden}"
        if yeni is None:
            rapor.append(satir)
            continue
        rapor.append(satir + f" ⇒ {yeni:.2f} TL")
        liste = min(max(f["liste"], yeni), max(u["tavan"], yeni))
        degisecek.append({"barcode": u["barkod"], "salePrice": yeni, "listPrice": round(liste, 2)})
        kayit.append([u["barkod"], u["ad"], f"{f['satis']:.2f}", f"{yeni:.2f}",
                      f"{u['taban']:.2f}", f"{u['tavan']:.2f}", neden])

    print("\n".join(rapor))
    with open(os.path.join(os.path.dirname(__file__), "buybox", "son_durum.md"), "w", encoding="utf-8") as f:
        f.write("# Buybox son durum" + (" (DENEME)" if deneme else "") + "\n\n" + "\n".join(rapor) + "\n")
    ozet_dosya = os.environ.get("GITHUB_STEP_SUMMARY")
    if ozet_dosya:
        with open(ozet_dosya, "a", encoding="utf-8") as f:
            f.write("### Buybox takibi" + (" (DENEME)" if deneme else "") + "\n\n" + "\n".join(rapor) + "\n")

    if not degisecek:
        print("Fiyat değişikliği yok.")
        return 0
    if deneme:
        print(f"DENEME: {len(degisecek)} fiyat değişecekti, gönderilmedi.")
        return 0

    r = _istek(s, "POST", FIYAT_API.format(sid=sid), json={"items": degisecek})
    print("Fiyat güncelleme:", r.status_code, r.text[:300])
    sonuc = "gönderildi"
    if r.ok:
        bid = r.json().get("batchRequestId")
        for _ in range(12):
            time.sleep(10)
            rr = _istek(s, "GET", BATCH_API.format(sid=sid, bid=bid))
            if rr.ok:
                v = rr.json()
                if v.get("status") != "IN_PROGRESS":
                    hatalar = [f"{i.get('requestItem', {}).get('barcode')}: {i.get('failureReasons')}"
                               for i in v.get("items", []) if i.get("status") != "SUCCESS"]
                    sonuc = "tamam" if not hatalar else "hata: " + "; ".join(hatalar)
                    break
    else:
        sonuc = f"hata {r.status_code}: {r.text[:150]}"
    print("Sonuç:", sonuc)
    kaydet([k + [sonuc] for k in kayit])
    return 0 if not sonuc.startswith("hata") else 1


if __name__ == "__main__":
    sys.exit(main())
