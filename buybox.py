"""Trendyol buybox fiyat takibi (Morro Tekstil) — tüm ürünler.

Her çalışmada:
  1. Trendyol API'sinden satıştaki tüm varyantlar okunur (ad, marka, kategori, stok kodu, fiyat).
  2. Maliyet ve DLAP fiyatı (tavan) buybox/maliyetler.csv'den stok koduna (yoksa barkoda) göre bulunur.
  3. Kural tipi ürünün marka/kategori/adından belirlenir (aşağıda), taban hesaplanır.
  4. Buybox bilgisi okunur, fiyat rakibin %1 altına ayarlanır:
       - Hiçbir zaman TABANIN altına inmez, hiçbir zaman TAVANIN (DLAP fiyatı) üstüne çıkmaz.
       - Rakip fiyat yükseltirse biz de yükseliriz.
       - Rakip yoksa fiyata dokunulmaz (tabanın altındaysa tabana çekilir).
       - Fiyatımız buybox fiyatından düşük olduğu halde buybox rakipteyse ek indirim yapılmaz.

Kural tipleri (kullanıcının kararları):
  kis300  : U.S. Polo kışlık (pijama / alt-üst takım / gecelik / ev giyim; kısa kollu ve boxer hariç)
            → en az 300 TL net kâr (ve en az %10). Bu ürünlerin hiçbiri 300 TL kârın altında satılmaz.
  basabas : Pierre Cardin sütyen ve sütyen takımları; U.S. Polo, Pierre Cardin ve Pijapia kısa kollu/yazlık
            → zarar etmesin yeter (stok eritme).
  normal  : diğer her şey → maliyet üzerinden %10 kâr.
  Morro markalı ürünlere hiç dokunulmaz.

  normal/basabas ürünlerde fiyat ŞU AN tabanın altındaysa kullanıcı onu bilerek eritiyordur: dokunulmaz.

buybox/istisnalar.csv ile tek tek barkod için kural değiştirilebilir veya ürün takipten çıkarılabilir
(flaş teklif, kampanya vb.): barkod,kural,aktif,not  (aktif=0 → dokunma; kural boşsa otomatik).

DENEME=1 ile çalıştırılırsa hiçbir fiyatı değiştirmez, sadece raporlar.
"""
import csv
import math
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta

from trendyol import _oturum, tum_varyantlar

KARGO = 98.34          # 81,95 TL + KDV, 3 desiye kadar
KOMISYON = 0.215       # %21,5
KAR_ORANI = 0.10
KIS_KAR_TL = 300.0
RAKIP_ALTI = 0.01
MIN_DEGISIM = 0.50

KLASOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buybox")
MALIYET_DOSYASI = os.path.join(KLASOR, "maliyetler.csv")
ISTISNA_DOSYASI = os.path.join(KLASOR, "istisnalar.csv")
KAYIT_KLASORU = os.path.join(KLASOR, "kayit")
TR = timezone(timedelta(hours=3))

BUYBOX_API = "https://apigw.trendyol.com/integration/product/sellers/{sid}/products/buybox-information"
FIYAT_API = "https://apigw.trendyol.com/integration/inventory/sellers/{sid}/products/price-and-inventory"
BATCH_API = "https://apigw.trendyol.com/integration/product/sellers/{sid}/products/batch-requests/{bid}"

YAZLIK = re.compile(r"kısa ?kol|yarım kol|kapri|şort takım|şortlu|şort-atlet|kolsuz|sıfır kol|atlet & şort")
KIS_KATEGORI = re.compile(r"pijama|alt - üst|gecelik|ev giyim")
SUTYEN_KATEGORI = re.compile(r"sütyen|iç çamaşırı takımı|fantezi jartiyer")


def kucuk(s):
    return str(s or "").replace("I", "ı").replace("İ", "i").lower()


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


def marka(v):
    b = v.get("brand") or v.get("brandName") or ""
    if isinstance(b, dict):
        b = b.get("name") or ""
    return str(b)


def kural_bul(v):
    ad, mk, kat = kucuk(v.get("title")), kucuk(marka(v)), kucuk(v.get("categoryName"))
    if "morro" in mk:
        return "morro"
    polo = "polo" in mk
    pc = "pierre cardin" in mk
    if polo and KIS_KATEGORI.search(kat) and not YAZLIK.search(ad) and "boxer" not in ad:
        return "kis300"
    if pc and ("sütyen" in ad or SUTYEN_KATEGORI.search(kat)):
        return "basabas"
    if (polo or pc or "pijapia" in mk) and YAZLIK.search(ad):
        return "basabas"
    return "normal"


def sayi(s):
    s = str(s or "").strip().replace(",", ".")
    return float(s) if s else None


def maliyetleri_oku():
    t = {}
    with open(MALIYET_DOSYASI, encoding="utf-8") as f:
        for s in csv.DictReader(f, delimiter=";"):
            t[s["stok_kodu"].strip()] = (sayi(s["maliyet"]), sayi(s["tavan"]))
    return t


def istisnalari_oku():
    t = {}
    if os.path.exists(ISTISNA_DOSYASI):
        with open(ISTISNA_DOSYASI, encoding="utf-8") as f:
            for s in csv.DictReader(f):
                b = (s.get("barkod") or "").strip()
                if b:
                    t[b] = {"kural": (s.get("kural") or "").strip().lower(),
                            "aktif": str(s.get("aktif", "1")).strip() != "0"}
    return t


def _istek(s, yontem, url, **kw):
    r = None
    for deneme in range(4):
        r = s.request(yontem, url, timeout=60, **kw)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(5 * (deneme + 1))
            continue
        return r
    return r


def buybox_bilgisi(s, sid, barkodlar):
    sonuc = {}
    for i in range(0, len(barkodlar), 10):
        parca = barkodlar[i:i + 10]
        r = _istek(s, "POST", BUYBOX_API.format(sid=sid), json={"barcodes": parca},
                   headers={"storeFrontCode": "TR"})
        if r is not None and r.ok:
            for x in r.json().get("buyboxInfo", []):
                sonuc[x["barcode"]] = x
        time.sleep(0.1)
    return sonuc


def hedef_fiyat(u, simdiki, bb):
    """(yeni_fiyat veya None, açıklama)"""
    sira = bb.get("buyboxOrder")
    bb_fiyat = float(bb.get("buyboxPrice") or 0)
    ikinci = float(bb.get("secondBuyboxPrice") or 0)
    coklu = bool(bb.get("hasMultipleSeller"))
    alt = simdiki < u["taban"] - 0.01

    if not coklu:
        return (u["taban"], "rakip yok, tabanın altındaydı → tabana") if alt else (None, "rakip yok")
    if sira == 1:
        if ikinci <= 0:
            return (u["taban"], "buybox bizde, tabanın altındaydı → tabana") if alt else (None, "buybox bizde")
        # Buybox bizdeyken fiyat düşürülmez; 2. satıcı yükseldiyse onun %1 altına kadar yükseltilir.
        hedef, neden = max(simdiki, ikinci * (1 - RAKIP_ALTI)), f"buybox bizde, 2. satıcı {ikinci:.2f}"
    else:
        if simdiki <= bb_fiyat + 0.01:
            if alt:
                return u["taban"], f"buybox rakipte ({bb_fiyat:.2f}), tabanın altındaydı → tabana"
            return None, "fiyat bizde ama buybox rakipte"
        if bb_fiyat * (1 - RAKIP_ALTI) < u["taban"]:
            # Rakip tabanımızın altında: tabana inip yine kaybetmenin anlamı yok.
            if alt:
                return u["taban"], f"rakip tabanın altında ({bb_fiyat:.2f}), fiyat tabanın altındaydı → tabana"
            return None, "rakip tabanın altında"
        hedef, neden = bb_fiyat * (1 - RAKIP_ALTI), f"buybox rakipte {bb_fiyat:.2f}"

    hedef = asagi(hedef)
    if hedef < u["taban"]:
        hedef, neden = u["taban"], neden + " → taban"
    tavan = max(u["tavan"], simdiki)   # tavan yalnızca yükseltmeyi sınırlar, fiyat tavana indirilmez
    if hedef > tavan:
        hedef, neden = tavan, neden + " → tavan"
    if abs(hedef - simdiki) < MIN_DEGISIM:
        return None, neden
    return hedef, neden


def kaydet(satirlar):
    if not satirlar:
        return
    os.makedirs(KAYIT_KLASORU, exist_ok=True)
    simdi = datetime.now(TR)
    yol = os.path.join(KAYIT_KLASORU, simdi.strftime("%Y-%m-%d") + ".csv")
    yeni = not os.path.exists(yol)
    with open(yol, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if yeni:
            w.writerow(["saat", "barkod", "ad", "kural", "eski", "yeni", "taban", "tavan", "neden", "sonuc"])
        for s in satirlar:
            w.writerow([simdi.strftime("%H:%M")] + s)


def main():
    deneme = os.environ.get("DENEME", "0") == "1"
    maliyetler = maliyetleri_oku()
    istisnalar = istisnalari_oku()
    s, sid = _oturum()

    sayac = {"morro": 0, "stoksuz": 0, "maliyet_yok": 0, "tavan_hatali": 0, "eritiliyor": 0,
             "istisna": 0, "takip": 0}
    kural_sayac = {"kis300": 0, "basabas": 0, "normal": 0}
    sorunlu, urunler = [], []
    for v in tum_varyantlar():
        if v.get("archived") or v.get("locked") or v.get("onSale") is False:
            continue
        b = v.get("barcode")
        if int(v.get("quantity") or 0) <= 0:
            sayac["stoksuz"] += 1
            continue
        ist = istisnalar.get(b, {})
        if ist and not ist["aktif"]:
            sayac["istisna"] += 1
            continue
        kural = ist.get("kural") or kural_bul(v)
        if kural == "morro":
            sayac["morro"] += 1
            continue
        m = maliyetler.get(str(v.get("stockCode") or "").strip()) or maliyetler.get(b)
        if not m or not m[0]:
            sayac["maliyet_yok"] += 1
            continue
        maliyet, tavan = m
        taban = taban_hesapla(maliyet, kural)
        simdiki = float(v.get("salePrice") or 0)
        ad = (v.get("title") or "").strip()[:70]
        if not tavan or tavan < taban:
            sayac["tavan_hatali"] += 1
            if len(sorunlu) < 15:
                sorunlu.append(f"- {ad} ({b}): DLAP fiyatı {tavan or 0:.2f} < taban {taban:.2f} — DLAP fiyatını/maliyeti kontrol et")
            continue
        if kural != "kis300" and simdiki < taban - 0.01 and not ist.get("kural"):
            sayac["eritiliyor"] += 1
            continue
        sayac["takip"] += 1
        kural_sayac[kural] += 1
        urunler.append({"barkod": b, "ad": ad, "kural": kural, "taban": taban, "tavan": tavan,
                        "satis": simdiki, "liste": float(v.get("listPrice") or 0)})

    bb = buybox_bilgisi(s, sid, [u["barkod"] for u in urunler])

    degisecek, kayit, rapor = [], [], []
    durum = {"bizde": 0, "rakipte": 0, "rakip_yok": 0, "bilgi_yok": 0, "yukari": 0, "asagi": 0}
    for u in urunler:
        x = bb.get(u["barkod"])
        if not x:
            durum["bilgi_yok"] += 1
            continue
        if not x.get("hasMultipleSeller"):
            durum["rakip_yok"] += 1
        elif x.get("buyboxOrder") == 1:
            durum["bizde"] += 1
        else:
            durum["rakipte"] += 1
        yeni, neden = hedef_fiyat(u, u["satis"], x)
        if yeni is None:
            continue
        durum["yukari" if yeni > u["satis"] else "asagi"] += 1
        liste = round(min(max(u["liste"], yeni), max(u["tavan"], yeni)), 2)
        degisecek.append({"barcode": u["barkod"], "salePrice": yeni, "listPrice": liste})
        kayit.append([u["barkod"], u["ad"], u["kural"], f"{u['satis']:.2f}", f"{yeni:.2f}",
                      f"{u['taban']:.2f}", f"{u['tavan']:.2f}", neden])
        rapor.append(f"- {u['ad']}: {u['satis']:.2f} ⇒ {yeni:.2f} TL ({u['kural']}, taban {u['taban']:.2f}) · {neden}")

    simdi = datetime.now(TR).strftime("%d.%m.%Y %H:%M")
    ozet = [f"# Buybox son durum{' (DENEME)' if deneme else ''}", "",
            f"Son kontrol: {simdi}", "",
            f"**Takip edilen: {sayac['takip']} varyant** (300 TL kâr: {kural_sayac['kis300']}, "
            f"%10 kâr: {kural_sayac['normal']}, başabaş: {kural_sayac['basabas']})", "",
            f"- Buybox bizde: {durum['bizde']}",
            f"- Buybox rakipte: {durum['rakipte']}",
            f"- Rakip yok: {durum['rakip_yok']}",
            f"- Buybox bilgisi alınamadı: {durum['bilgi_yok']}",
            f"- Bu kontrolde fiyatı değişen: {len(degisecek)} (yükselen {durum['yukari']}, düşen {durum['asagi']})", "",
            "Takibe alınmayanlar:",
            f"- Morro: {sayac['morro']} · stok yok: {sayac['stoksuz']} · maliyet yok: {sayac['maliyet_yok']}",
            f"- Bilerek eritilen (fiyat zaten tabanın altında): {sayac['eritiliyor']}",
            f"- DLAP fiyatı tabanın altında (kontrol gerekli): {sayac['tavan_hatali']}",
            f"- İstisna listesiyle kapatılan: {sayac['istisna']}", ""]
    if sorunlu:
        ozet += ["## Kontrol edilmesi gerekenler", ""] + sorunlu + [""]
    if rapor:
        ozet += ["## Değişiklikler", ""] + rapor[:300] + ([f"- … ve {len(rapor) - 300} değişiklik daha"] if len(rapor) > 300 else []) + [""]
    metin = "\n".join(ozet)
    print(metin)
    with open(os.path.join(KLASOR, "son_durum.md"), "w", encoding="utf-8") as f:
        f.write(metin)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(metin)

    if not degisecek or deneme:
        return 0

    hata_var = False
    for k in range(0, len(degisecek), 500):
        parca, kparca = degisecek[k:k + 500], kayit[k:k + 500]
        r = _istek(s, "POST", FIYAT_API.format(sid=sid), json={"items": parca})
        print("Fiyat güncelleme:", r.status_code, r.text[:200])
        hatali, sonuc = {}, "gönderildi"
        if r.ok:
            bid = r.json().get("batchRequestId")
            for _ in range(18):
                time.sleep(10)
                rr = _istek(s, "GET", BATCH_API.format(sid=sid, bid=bid))
                if rr is not None and rr.ok and rr.json().get("status") != "IN_PROGRESS":
                    for it in rr.json().get("items", []):
                        if it.get("status") != "SUCCESS":
                            hatali[(it.get("requestItem") or {}).get("barcode")] = str(it.get("failureReasons"))[:120]
                    sonuc = "tamam"
                    break
        else:
            sonuc = f"hata {r.status_code}: {r.text[:120]}"
        if hatali or sonuc.startswith("hata"):
            hata_var = True
        kaydet([kk + [("hata: " + hatali[kk[0]]) if kk[0] in hatali else sonuc] for kk in kparca])
        time.sleep(1)
    return 1 if hata_var else 0


if __name__ == "__main__":
    sys.exit(main())
