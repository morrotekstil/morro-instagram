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


def soyutla(img: Image.Image):
    """(soyut_görsel, kiyafet_orani) döndürür; kıyafet bulunamazsa (None, 0)."""
    img = img.convert("RGB")
    kucuk = ImageOps.contain(img, (768, 768))
    et = _etiketler(kucuk)
    maske = np.isin(et, KIYAFET)
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
