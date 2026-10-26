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


def detaylar(u):
    """Gönderi ve hikayede gösterilecek (etiket, değer) listesi. Fiyat yok."""
    oz = u.get("ozellikler") or {}
    out = []
    if u.get("renkler"):
        out.append(("🎨", "Renk", ", ".join(u["renkler"][:6])))
    if u.get("stoklu_beden"):
        out.append(("📏", "Beden", ", ".join(u["stoklu_beden"][:10])))
    icerik = oz.get("Materyal Bileşeni") or oz.get("Materyal")
    if icerik:
        out.append(("🧵", "Kumaş içeriği", icerik))
    if oz.get("Kumaş Tipi"):
        out.append(("🪡", "Kumaş tipi", oz["Kumaş Tipi"]))
    if oz.get("Paket İçeriği") and oz["Paket İçeriği"].lower() != "tekli":
        out.append(("📦", "Paket içeriği", oz["Paket İçeriği"]))
    for ad, ik in (("Kalıp", "👕"), ("Bel", "📐"), ("Yaka Tipi", "👔"), ("Kol Boyu", "💪"),
                   ("Paça Tipi", "👖"), ("Ek Özellik", "✅"), ("Ürün Detayı", "🔎")):
        if oz.get(ad):
            out.append((ik, ad, oz[ad]))
    return out


def aciklama(u, yuzde=0):
    satirlar = [u["baslik"], "", "✨ Ürün özellikleri"]
    for ik, ad, deger in detaylar(u):
        satirlar.append(f"{ik} {ad}: {deger}")
    satirlar += [
        "",
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
    for kod in (u["id"], u.get("model")):
        if not kod:
            continue
        ana = klasor / f"{kod}.jpg"
        ekler = sorted(klasor.glob(f"{kod}-*.jpg"))
        if ana.exists() or ekler:
            break
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


def son_modeller(gecmis, gun):
    sinir = (D.simdi() - dt.timedelta(days=gun)).date().isoformat()
    return {p.get("model") or p["urun_id"].split("~")[0] for p in gecmis if p["tarih"] >= sinir}


def morro_mu(u):
    return A.MORRO_MARKA in kucuk(u.get("marka"))


def sec(urunler, gecmis, adet, tekrar_gun=None):
    yakin = son_paylasilanlar(gecmis, tekrar_gun or A.TEKRAR_GUN)
    if not A.SOYUTLA:
        urunler = [u for u in urunler if uygun_mu(u)]
    yakin_model = son_modeller(gecmis, A.MODEL_ARA_GUN)
    adaylar = [u for u in urunler
               if u["stok"] >= A.MIN_STOK and u["gorseller"] and u["id"] not in yakin
               and u.get("model", u["id"]) not in yakin_model]
    if len(adaylar) < adet:  # ürün azsa tekrar sınırını gevşet
        yakin7 = son_paylasilanlar(gecmis, min(7, tekrar_gun or 7))
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
    gorulen, tekil = set(), []
    for u in adaylar:  # aynı günde aynı modelin tek rengi
        m = u.get("model", u["id"])
        if m not in gorulen:
            gorulen.add(m)
            tekil.append(u)
    adaylar = tekil
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


def kalem(u, saat, sira, tarih, tur="gonderi", grup="diger"):
    etiket, yuzde = gorsel.etiket_metni(u["fiyat"], u["liste_fiyat"])
    ozel = ozel_gorseller(u)
    soyut_mu = hassas_mi(u)
    kaynaklar = ozel if ozel else u["gorseller"]
    foto = 1 if tur == "hikaye" else A.FOTO_SAYISI
    hazir = []  # (öncelik, görsel)
    for j, kaynak in enumerate(kaynaklar[:foto + (3 if soyut_mu else 0)], start=1):
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
    for _, _, img in (hazir[:A.FOTO_SAYISI] if tur == "gonderi" else []):
        dosya = f"media/{tarih}-{sira}-{len(dosyalar) + 1}.jpg"
        gorsel.hazirla(img, etiket if not dosyalar else None, D.KOK / dosya)
        dosyalar.append(dosya)
    if not hazir:
        raise RuntimeError("kullanılabilir görsel çıkmadı")
    dosya = dosyalar[0] if dosyalar else None
    hikaye_dosya = None
    if A.HIKAYE or tur == "hikaye":
        try:
            hikaye_dosya = f"media/{tarih}-{sira}-hikaye.jpg"
            gorsel.hikaye(hazir[0][2], u["baslik"], detaylar(u), D.KOK / hikaye_dosya)
        except Exception:
            if tur == "hikaye":
                raise
            hikaye_dosya = None
    return {
        "saat": saat, "durum": "bekliyor", "tur": tur, "grup": grup,
        "marka": u.get("marka"),
        "urun_id": u["id"], "model": u.get("model"), "baslik": u["baslik"], "kategori": u["kategori"],
        "fiyat": u["fiyat"], "liste_fiyat": u["liste_fiyat"], "stok": u["stok"],
        "etiket": etiket, "aciklama": aciklama(u, yuzde),
        "gorsel": dosya, "gorsel_url": f"{A.HAM_ADRES}/{dosya}" if dosya else None,
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
    kalemler, yedekler = [], []
    sira = 1
    for grup in ("morro", "diger"):
        slotlar = [p for p in A.PROGRAM if p[2] == grup]
        if not slotlar:
            continue
        havuz = [u for u in urunler if morro_mu(u) == (grup == "morro")]
        tekrar = A.MORRO_TEKRAR_GUN if grup == "morro" else A.TEKRAR_GUN
        hedef = len(slotlar) + A.YEDEK_SAYISI
        secim = sec(havuz, gecmis, hedef + 4, tekrar)  # görseli çıkmayanların yerine fazladan aday
        dolu, yedek_say = 0, 0
        for u in secim:
            if dolu >= len(slotlar) and yedek_say >= A.YEDEK_SAYISI:
                break
            saat, tur, _ = slotlar[dolu] if dolu < len(slotlar) else (None, "gonderi", grup)
            try:
                k = kalem(u, saat, sira, tarih, tur, grup)
                sira += 1
                if saat:
                    kalemler.append(k)
                    dolu += 1
                else:
                    k["durum"] = "yedek"
                    yedekler.append(k)
                    yedek_say += 1
            except Exception as e:
                notlar.append(f"{u['baslik'][:40]}: görsel hazırlanamadı ({e})")
        if dolu < len(slotlar):
            notlar.append(f"{grup}: {len(slotlar) - dolu} saat için uygun ürün bulunamadı")
    kalemler.sort(key=lambda k: k["saat"])

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
        print(f"  {k['saat']}  {k['tur']:7} {k['grup']:5}  {k['baslik'][:60]}")
    for n in notlar:
        print("  not:", n)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
