"""Günlük plan: her sabah 3 ürün (+ yedekler) seçer, görsellerini hazırlar,
geçmiş paylaşımların fiyat değişikliklerini kontrol eder.

Sonuç plan/GGGG-AA-GG.json ve plan/bugun.json dosyalarına yazılır;
sabah raporu bu dosyayı okuyarak önizleme gösterir.
"""
import datetime as dt
import math
import random
import sys
import traceback

import ayarlar as A
import durum as D
import gorsel
import instagram
import trendyol


def fiyat_yaz(x):
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s[:-3] if s.endswith(",00") else s


def hashtagler(baslik):
    b = baslik.lower()
    ek = []
    for k, v in A.ETIKETLER.items():
        if k in b:
            ek.extend(t for t in v.split() if t not in ek)
    return " ".join(ek[:10] + A.SABIT_ETIKETLER.split())


def aciklama(u, yuzde):
    satirlar = [u["baslik"], ""]
    if yuzde:
        satirlar.append(f"💰 {fiyat_yaz(u['liste_fiyat'])} TL yerine {fiyat_yaz(u['fiyat'])} TL")
    else:
        satirlar.append(f"💰 {fiyat_yaz(u['fiyat'])} TL")
    if u.get("stoklu_beden"):
        satirlar.append("📏 Bedenler: " + ", ".join(u["stoklu_beden"][:8]))
    satirlar += [
        "🚚 Stokta, hızlı kargo",
        "🛒 Trendyol'da Morro mağazamızda. Link profilde!",
        "",
        hashtagler(u["baslik"]),
    ]
    return "\n".join(satirlar)


def kucuk(m):
    return (m or "").replace("İ", "i").replace("I", "ı").lower()


def ozel_gorseller(u):
    """ozel/<kod>.jpg, ozel/<kod>-2.jpg ... dosyaları (varsa)."""
    klasor = D.KOK / "ozel"
    if not klasor.exists():
        return []
    ana = klasor / f"{u['id']}.jpg"
    ekler = sorted(klasor.glob(f"{u['id']}-*.jpg"))
    return ([ana] if ana.exists() else []) + ekler


def ozel_gorsel(u):
    o = ozel_gorseller(u)
    return o[0] if o else None


def hassas_mi(u):
    """Mankenli kadın iç çamaşırı ürünü mü (ve özel görseli yok mu)?"""
    metin = kucuk(u["baslik"]) + " " + kucuk(str(u["kategori"]))
    if "erkek" in metin or ozel_gorsel(u) is not None:
        return False
    return any(k in metin for k in A.HASSAS_KELIMELER)


def uygun_mu(u):
    return not hassas_mi(u)


def son_paylasilanlar(gecmis, gun):
    sinir = (D.simdi() - dt.timedelta(days=gun)).date().isoformat()
    return {p["urun_id"] for p in gecmis if p["tarih"] >= sinir}


def sec(urunler, gecmis, adet):
    yakin = son_paylasilanlar(gecmis, A.TEKRAR_GUN)
    if not A.SOYUTLA:
        urunler = [u for u in urunler if uygun_mu(u)]
    adaylar = [u for u in urunler
               if u["stok"] >= A.MIN_STOK and u["gorseller"] and u["id"] not in yakin]
    if len(adaylar) < adet:  # ürün azsa tekrar sınırını gevşet
        yakin7 = son_paylasilanlar(gecmis, 7)
        adaylar = [u for u in urunler
                   if u["stok"] >= A.MIN_STOK and u["gorseller"] and u["id"] not in yakin7]
    rnd = random.Random(D.bugun())

    def puan(u):
        indirim = (1 - u["fiyat"] / u["liste_fiyat"]) * 100 if u["liste_fiyat"] else 0
        return indirim * 0.08 + math.log10(u["stok"] + 1) + rnd.random() * 2

    adaylar.sort(key=puan, reverse=True)
    hassas_say, sinirli = 0, []
    for u in adaylar:  # günlük hassas ürün sınırı
        if hassas_mi(u):
            if hassas_say >= A.GUNLUK_HASSAS:
                continue
            hassas_say += 1
        sinirli.append(u)
    adaylar = sinirli
    secilen, kategoriler = [], set()
    for u in adaylar:  # önce farklı kategorilerden
        if u["kategori"] not in kategoriler:
            secilen.append(u)
            kategoriler.add(u["kategori"])
        if len(secilen) == adet:
            return secilen
    for u in adaylar:
        if u not in secilen:
            secilen.append(u)
        if len(secilen) == adet:
            break
    return secilen


def fiyat_degisiklikleri(urunler, gecmis):
    sinir = (D.simdi() - dt.timedelta(days=A.FIYAT_TAKIP_GUN)).date().isoformat()
    guncel = {u["id"]: u for u in urunler}
    sonuc, gorulen = [], set()
    for p in sorted(gecmis, key=lambda p: p["tarih"], reverse=True):
        if p["tarih"] < sinir or p["urun_id"] in gorulen:
            continue
        gorulen.add(p["urun_id"])
        u = guncel.get(p["urun_id"])
        if not u:
            continue
        if abs(u["fiyat"] - p["fiyat"]) >= 1:
            sonuc.append({
                "baslik": p["baslik"], "paylasim_tarihi": p["tarih"],
                "paylasilan_fiyat": p["fiyat"], "guncel_fiyat": u["fiyat"],
                "instagram": p.get("permalink"),
            })
    return sonuc


def kalem(u, saat, sira, tarih):
    etiket, yuzde = gorsel.etiket_metni(u["fiyat"], u["liste_fiyat"])
    ozel = ozel_gorseller(u)
    soyut_mu = hassas_mi(u)
    kaynaklar = ozel if ozel else u["gorseller"]
    hazir = []  # (öncelik, görsel)
    for j, kaynak in enumerate(kaynaklar[:A.FOTO_SAYISI + (3 if soyut_mu else 0)], start=1):
        try:
            img = gorsel.ac(kaynak) if ozel else gorsel.indir(kaynak)
            oncelik = 1
            if soyut_mu:  # mankeni cansız mankene çevir, pantolon vb. çıkar
                import soyutla
                img, oran = soyutla.manken(img, u["baslik"])
                if img is None or oran < 0.03:
                    continue
                oncelik = 0 if getattr(img, "insansiz", False) else 1
            hazir.append((oncelik, j, img))
        except Exception:
            if j == 1 and not soyut_mu:
                raise
            continue
    hazir.sort(key=lambda t: (t[0], t[1]))  # ürünün tek başına olduğu kareler önce
    dosyalar = []
    for _, _, img in hazir[:A.FOTO_SAYISI]:
        dosya = f"media/{tarih}-{sira}-{len(dosyalar) + 1}.jpg"
        gorsel.hazirla(img, etiket if not dosyalar else None, D.KOK / dosya)
        dosyalar.append(dosya)
    if not dosyalar:
        raise RuntimeError("kullanılabilir görsel çıkmadı")
    dosya = dosyalar[0]
    hikaye_dosya = None
    if A.HIKAYE:
        try:
            hikaye_dosya = f"media/{tarih}-{sira}-hikaye.jpg"
            gorsel.hikaye(hazir[0][2], u["baslik"], u["fiyat"], u["liste_fiyat"], D.KOK / hikaye_dosya)
        except Exception:
            hikaye_dosya = None
    return {
        "saat": saat, "durum": "bekliyor",
        "urun_id": u["id"], "baslik": u["baslik"], "kategori": u["kategori"],
        "fiyat": u["fiyat"], "liste_fiyat": u["liste_fiyat"], "stok": u["stok"],
        "etiket": etiket, "aciklama": aciklama(u, yuzde),
        "gorsel": dosya, "gorsel_url": f"{A.HAM_ADRES}/{dosya}",
        "gorsel_urls": [f"{A.HAM_ADRES}/{d}" for d in dosyalar],
        "manken_silindi": soyut_mu,
        "hikaye_url": f"{A.HAM_ADRES}/{hikaye_dosya}" if hikaye_dosya else None,
        "kaynak_gorsel": u["gorseller"][0], "link": u.get("link"),
    }


def main():
    tarih = D.bugun()
    gecmis = D.oku(D.GECMIS, [])
    notlar = []

    # Token'ı birkaç günde bir uzat (60 günlük süre hiç dolmasın)
    try:
        if not A.DRY_RUN and D.token_yenilenmeli():
            yeni, sure = instagram.yenile(D.token_al())
            D.token_kaydet(yeni, sure)
            notlar.append("Instagram token'ı yenilendi")
    except Exception as e:  # plan yine de çıksın
        notlar.append(f"Token yenilenemedi: {e}")

    # 7 günden eski görselleri sil (depo şişmesin)
    sinir = (D.simdi() - dt.timedelta(days=7)).date().isoformat()
    for f in (D.KOK / "media").glob("*.jpg"):
        if f.name[:10] < sinir:
            f.unlink()

    urunler = trendyol.urunler()
    hedef = len(A.SAATLER) + A.YEDEK_SAYISI
    secim = sec(urunler, gecmis, hedef + 4)  # görseli çıkmayanların yerine fazladan aday
    kalemler, yedekler = [], []
    sira = 1
    for u in secim:
        if len(kalemler) + len(yedekler) >= hedef:
            break
        try:
            saat = A.SAATLER[len(kalemler)] if len(kalemler) < len(A.SAATLER) else None
            k = kalem(u, saat, sira, tarih)
            sira += 1
            (kalemler if saat else yedekler).append(k)
        except Exception as e:
            notlar.append(f"{u['baslik'][:40]}: görsel hazırlanamadı ({e})")
    for y in yedekler:
        y["durum"] = "yedek"

    plan = {
        "tarih": tarih,
        "olusturma": D.simdi().isoformat(timespec="minutes"),
        "paylasimlar": kalemler,
        "yedekler": yedekler,
        "fiyat_degisiklikleri": fiyat_degisiklikleri(urunler, gecmis),
        "stoktaki_urun_sayisi": sum(1 for u in urunler if u["stok"] >= A.MIN_STOK),
        "notlar": notlar,
    }
    D.yaz(D.plan_yolu(tarih), plan)
    D.yaz(D.KOK / "plan" / "bugun.json", plan)
    print(f"Plan hazır: {len(kalemler)} paylaşım, {len(yedekler)} yedek, "
          f"{len(plan['fiyat_degisiklikleri'])} fiyat değişikliği")
    for k in kalemler:
        print(f"  {k['saat']}  {k['baslik'][:60]}  {k['fiyat']} TL  [{k['etiket']}]")
    for n in notlar:
        print("  not:", n)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
