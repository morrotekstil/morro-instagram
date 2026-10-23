"""Mankeni soyutlama: fotoğraftaki kıyafeti (sütyen, külot, takım...) kesip
mankeni (ten, yüz, saç, kollar, bacaklar) tamamen kaldırır; ürünü sade bir
zemin üzerinde "görünmez manken" tarzında ortalar.

Yapay zeka modeli: mattmdjaga/segformer_b2_clothes (ücretsiz, GitHub'da çalışır).
"""
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFilter, ImageOps

import ayarlar as A

# Modelin sınıfları: 0 arka plan, 1 şapka, 2 saç, 3 gözlük, 4 üst giysi, 5 etek,
# 6 pantolon, 7 elbise, 8 kemer, 9-10 ayakkabı, 11 yüz, 12-13 bacak, 14-15 kol,
# 16 çanta, 17 atkı
KIYAFET = [4, 5, 6, 7, 8, 17]
TEN = [2, 11, 12, 13, 14, 15]
ZEMIN = (246, 243, 239)


@lru_cache(maxsize=1)
def _model():
    from transformers import SegformerImageProcessor, AutoModelForSemanticSegmentation
    ad = "mattmdjaga/segformer_b2_clothes"
    return SegformerImageProcessor.from_pretrained(ad), AutoModelForSemanticSegmentation.from_pretrained(ad)


def _etiketler(img):
    import torch
    isl, model = _model()
    with torch.no_grad():
        cikti = model(**isl(images=img, return_tensors="pt"))
    up = torch.nn.functional.interpolate(cikti.logits, size=img.size[::-1],
                                         mode="bilinear", align_corners=False)
    return up.argmax(dim=1)[0].numpy()


def _temizle(maske):
    """Kenarlarda kalan küçük ten parçalarını atar, delikleri kapatır."""
    from scipy import ndimage
    maske = ndimage.binary_opening(maske, iterations=2)
    etiket, n = ndimage.label(maske)
    if n == 0:
        return maske
    boyutlar = ndimage.sum(maske, etiket, range(1, n + 1))
    en_buyuk = boyutlar.max()
    tut = [i + 1 for i, b in enumerate(boyutlar) if b >= en_buyuk * 0.15]
    maske = np.isin(etiket, tut)
    maske = ndimage.binary_closing(maske, iterations=3)
    return ndimage.binary_fill_holes(maske)


def soyutla(img: Image.Image):
    """(soyut_görsel, kiyafet_orani) döndürür; kıyafet bulunamazsa (None, 0)."""
    img = img.convert("RGB")
    kucuk = ImageOps.contain(img, (768, 768))
    et = _etiketler(kucuk)
    maske = _temizle(np.isin(et, KIYAFET))
    oran = float(maske.mean())
    if oran < 0.01:
        return None, 0.0
    m = Image.fromarray((maske * 255).astype("uint8")).resize(img.size, Image.LANCZOS)
    m = m.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.2))
    kutu = m.getbbox()
    if not kutu:
        return None, 0.0
    kiyafet = Image.new("RGB", img.size, ZEMIN)
    kiyafet.paste(img, (0, 0), m)
    kiyafet = kiyafet.crop(kutu)
    # yumuşak gölge ile zemine oturt
    W, H = A.GENISLIK, A.YUKSEKLIK
    alan = ImageOps.contain(kiyafet, (int(W * 0.78), int(H * 0.70)), Image.LANCZOS)
    mk = ImageOps.contain(m.crop(kutu), alan.size, Image.LANCZOS)
    tuval = Image.new("RGB", (W, H), ZEMIN)
    x, y = (W - alan.width) // 2, (H - alan.height) // 2
    golge = Image.new("L", (W, H), 0)
    golge.paste(mk, (x + 10, y + 16))
    golge = golge.filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.28))
    tuval = Image.composite(Image.new("RGB", (W, H), (120, 110, 100)), tuval, golge)
    tuval.paste(alan, (x, y), mk)
    return tuval, oran


def ten_orani(img: Image.Image):
    """Fotoğrafta ne kadar çıplak ten/insan olduğunu ölçer (0-1)."""
    et = _etiketler(ImageOps.contain(img.convert("RGB"), (512, 512)))
    return float(np.isin(et, TEN).mean())


# --- Cansız manken ---------------------------------------------------------
# Kişinin silüeti açık renkli, mat bir cansız mankene dönüştürülür; baş kaldırılır,
# ürün dışındaki kıyafetler (pantolon, tişört vb.) de mankenin parçası olur.
# Sadece ürün (sütyen / külot / takım) orijinal haliyle kalır.

MANKEN_RENK = np.array([236, 232, 226], dtype=float)
ZEMIN2 = (243, 240, 236)


def urun_turu(baslik):
    b = (baslik or "").replace("İ", "i").replace("I", "ı").lower()
    if "takım" in b or "takim" in b or ("sütyen" in b and "külot" in b):
        return "takim"
    if any(k in b for k in ("sütyen", "bralet", "büstiyer")):
        return "ust"
    if any(k in b for k in ("külot", "string", "tanga", "slip")):
        return "alt"
    if any(k in b for k in ("body", "gecelik", "babydoll", "korse", "mayo", "bikini")):
        return "tam"
    return "takim"


def _kucuk_alt(alt, yukseklik):
    """Külot gibi küçük alt parçaları tutar; pantolon/etek gibi uzunları atar."""
    from scipy import ndimage
    et, n = ndimage.label(alt)
    tut = np.zeros_like(alt)
    for i in range(1, n + 1):
        ys, xs = np.where(et == i)
        h = ys.max() - ys.min()
        if h < yukseklik * 0.22 and ys.max() < yukseklik * 0.95 and len(ys) > 200:
            tut |= et == i
    return tut


def manken(img: Image.Image, baslik=""):
    """(manken_gorsel, urun_orani) döndürür; ürün bulunamazsa (None, 0)."""
    from scipy import ndimage
    img = img.convert("RGB")
    kucuk = ImageOps.contain(img, (900, 900))
    et = _etiketler(kucuk)
    H, W = et.shape
    tur = urun_turu(baslik)

    ust = _temizle(et == 4)
    alt = _kucuk_alt(np.isin(et, [5, 6]), H)
    if tur == "ust":
        urun = ust
    elif tur == "alt":
        urun = alt
    elif tur == "tam":
        urun = _temizle(np.isin(et, [4, 5, 7]))
    else:
        urun = ust | alt
    oran = float(urun.mean())
    if oran < 0.01:
        return None, 0.0

    # Silüet: arka plan dışındaki her şey, baş hariç
    bas = np.isin(et, [1, 2, 3, 11])
    sil = (et != 0) & ~bas
    sil = ndimage.binary_opening(sil, iterations=2)
    sil = ndimage.binary_fill_holes(ndimage.binary_closing(sil, iterations=4))
    etk, n = ndimage.label(sil)
    if n:
        boy = ndimage.sum(sil, etk, range(1, n + 1))
        sil = etk == (int(np.argmax(boy)) + 1)
    sil |= urun

    # Manken yüzeyi: orijinal ışık-gölgeyi yumuşatıp mat plastik dokusu ver
    gri = np.asarray(kucuk.convert("L").filter(ImageFilter.GaussianBlur(7)), dtype=float)
    if sil.any():
        lo, hi = np.percentile(gri[sil], [5, 95])
    else:
        lo, hi = 0, 255
    g = np.clip((gri - lo) / max(hi - lo, 1), 0, 1)
    golge = 0.80 + 0.28 * g
    yuzey = np.clip(MANKEN_RENK[None, None, :] * golge[..., None], 0, 255)

    tuval = np.empty((H, W, 3), dtype=float)
    tuval[:] = ZEMIN2
    sil_y = np.asarray(Image.fromarray((sil * 255).astype("uint8"))
                       .filter(ImageFilter.GaussianBlur(1.5)), dtype=float)[..., None] / 255
    tuval = tuval * (1 - sil_y) + yuzey * sil_y
    # ince kontur
    kenar = sil ^ ndimage.binary_erosion(sil, iterations=2)
    tuval[kenar] = tuval[kenar] * 0.88
    # ürün orijinal haliyle
    orj = np.asarray(kucuk, dtype=float)
    u_y = np.asarray(Image.fromarray((urun * 255).astype("uint8"))
                     .filter(ImageFilter.GaussianBlur(1.0)), dtype=float)[..., None] / 255
    tuval = tuval * (1 - u_y) + orj * u_y
    sonuc = Image.fromarray(tuval.astype("uint8"))

    # mankeni ortala
    kutu = Image.fromarray((sil * 255).astype("uint8")).getbbox() or (0, 0, W, H)
    pay = 30
    kutu = (max(kutu[0] - pay, 0), max(kutu[1] - pay, 0), min(kutu[2] + pay, W), min(kutu[3] + pay, H))
    sonuc = sonuc.crop(kutu)
    CW, CH = A.GENISLIK, A.YUKSEKLIK
    alan = ImageOps.contain(sonuc, (int(CW * 0.92), int(CH * 0.92)), Image.LANCZOS)
    son = Image.new("RGB", (CW, CH), ZEMIN2)
    son.paste(alan, ((CW - alan.width) // 2, (CH - alan.height) // 2))
    return son, oran
