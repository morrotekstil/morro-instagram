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


def guncel_fiyatlar(barkodlar):
    """barkod -> {satis, liste, stok, satista} (tüm onaylı ürünler tek seferde okunur)"""
    from trendyol import tum_varyantlar
    istenen = set(barkodlar)
    sonuc = {}
    for v in tum_varyantlar():
        b = v.get("barcode")
        if b in istenen:
            sonuc[b] = {"satis": float(v.get("salePrice") or 0),
                        "liste": float(v.get("listPrice") or 0),
                        "stok": int(v.get("quantity") or 0),
                        "satista": v.get("onSale") is not False and not v.get("archived") and not v.get("locked")}
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
        if simdiki < u["taban"] - 0.01:
            return u["taban"], "rakip yok, fiyat tabanın altındaydı → tabana"
        return None, "rakip yok → dokunulmadı"
    elif sira == 1:
        if ikinci > 0:
            hedef, neden = ikinci * (1 - RAKIP_ALTI), f"buybox bizde, 2. satıcı {ikinci:.2f}"
        else:
            if simdiki < u["taban"] - 0.01:
                return u["taban"], "buybox bizde, 2. fiyat yok, tabanın altındaydı → tabana"
            return None, "buybox bizde, 2. fiyat yok → dokunulmadı"
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
    fiyatlar = guncel_fiyatlar(barkodlar)
    bb = buybox_bilgisi(s, sid, barkodlar)

    degisecek, rapor, kayit = [], [], []
    sayac = {"bizde": 0, "rakipte": 0, "rakip_yok": 0, "atlandi": 0}
    for u in urunler:
        f, b = fiyatlar.get(u["barkod"]), bb.get(u["barkod"])
        if not f or not b or not f["satista"] or f["stok"] <= 0:
            sayac["atlandi"] += 1
            continue
        if not b.get("hasMultipleSeller"):
            sayac["rakip_yok"] += 1
        elif b.get("buyboxOrder") == 1:
            sayac["bizde"] += 1
        else:
            sayac["rakipte"] += 1
        yeni, neden = hedef_fiyat(u, f, b)
        if yeni is None:
            continue
        rapor.append(f"- {u['ad'] or u['barkod']}: {f['satis']:.2f} ⇒ {yeni:.2f} TL "
                     f"(taban {u['taban']:.2f}, tavan {u['tavan']:.2f}) · {neden}")
        liste = min(max(f["liste"], yeni), max(u["tavan"], yeni))
        degisecek.append({"barcode": u["barkod"], "salePrice": yeni, "listPrice": round(liste, 2)})
        kayit.append([u["barkod"], u["ad"], f"{f['satis']:.2f}", f"{yeni:.2f}",
                      f"{u['taban']:.2f}", f"{u['tavan']:.2f}", neden])

    simdi = datetime.now(TR).strftime("%d.%m.%Y %H:%M")
    ozet = (f"# Buybox son durum{' (DENEME)' if deneme else ''}\n\n"
            f"Son kontrol: {simdi} · takip edilen {len(urunler)} varyant\n\n"
            f"- Buybox bizde: {sayac['bizde']}\n- Buybox rakipte (taban/indirim yok kuralı): {sayac['rakipte']}\n"
            f"- Rakip yok: {sayac['rakip_yok']}\n- Satışta değil / stok yok / bulunamadı: {sayac['atlandi']}\n"
            f"- Bu kontrolde fiyatı değişen: {len(degisecek)}\n\n"
            + ("## Değişiklikler\n\n" + "\n".join(rapor) + "\n" if rapor else ""))
    print(ozet)
    with open(os.path.join(os.path.dirname(__file__), "buybox", "son_durum.md"), "w", encoding="utf-8") as f:
        f.write(ozet)
    ozet_dosya = os.environ.get("GITHUB_STEP_SUMMARY")
    if ozet_dosya:
        with open(ozet_dosya, "a", encoding="utf-8") as f:
            f.write(ozet)

    if not degisecek:
        return 0
    if deneme:
        print(f"DENEME: {len(degisecek)} fiyat değişecekti, gönderilmedi.")
        return 0

    hata_var = False
    for k in range(0, len(degisecek), 500):
        parca, kparca = degisecek[k:k + 500], kayit[k:k + 500]
        r = _istek(s, "POST", FIYAT_API.format(sid=sid), json={"items": parca})
        print("Fiyat güncelleme:", r.status_code, r.text[:200])
        hatali = {}
        sonuc = "gönderildi"
        if r.ok:
            bid = r.json().get("batchRequestId")
            for _ in range(18):
                time.sleep(10)
                rr = _istek(s, "GET", BATCH_API.format(sid=sid, bid=bid))
                if rr.ok and rr.json().get("status") != "IN_PROGRESS":
                    for it in rr.json().get("items", []):
                        if it.get("status") != "SUCCESS":
                            hatali[(it.get("requestItem") or {}).get("barcode")] = str(it.get("failureReasons"))[:120]
                    sonuc = "tamam"
                    break
        else:
            sonuc = f"hata {r.status_code}: {r.text[:120]}"
        if hatali or sonuc.startswith("hata"):
            hata_var = True
        kaydet([kk + ["hata: " + hatali[kk[0]] if kk[0] in hatali else sonuc] for kk in kparca])
        time.sleep(1)
    return 1 if hata_var else 0


if __name__ == "__main__":
    sys.exit(main())
