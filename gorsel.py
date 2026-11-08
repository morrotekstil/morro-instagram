"""Ürün görselini Instagram'a uygun hale getirir ve etiket ekler."""
import io
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import ayarlar as A

FONT_DIR = Path(__file__).parent / "fonts"


def _font(boyut, kalin=True):
    ad = "Poppins-Bold.ttf" if kalin else "Poppins-Medium.ttf"
    return ImageFont.truetype(str(FONT_DIR / ad), boyut)


def indir(url):
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content))
    img = ImageOps.exif_transpose(img).convert("RGB")
    return img


def ac(yol):
    return ImageOps.exif_transpose(Image.open(yol)).convert("RGB")


LOGO = Path(__file__).parent / "logo.png"


def _logo_yapistir(arka, ortala=False):
    """logo.png varsa sol üst köşeye beyaz zemin üzerinde logoyu koyar."""
    logo = Image.open(LOGO).convert("RGBA")
    logo = ImageOps.contain(logo, (300, 120), Image.LANCZOS)
    px, py, x0, y0 = 28, 20, 48, 56
    kutu = Image.new("RGBA", (logo.width + 2 * px, logo.height + 2 * py), (0, 0, 0, 0))
    ImageDraw.Draw(kutu).rounded_rectangle((0, 0, kutu.width - 1, kutu.height - 1),
                                           radius=26, fill=(255, 255, 255, 235))
    kutu.paste(logo, (px, py), logo)
    if ortala:
        x0 = (arka.width - kutu.width) // 2
    arka.paste(kutu, (x0, y0), kutu)


SITE = "morro.com.tr"


def _dunya_ikon(cap, renk):
    """Web sitesi simgesi (küre). Yumuşak kenar için 4 kat büyük çizilip küçültülür."""
    K = 4
    c = cap * K
    im = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = max(2, int(c * 0.075))
    d.ellipse((w // 2, w // 2, c - w // 2 - 1, c - w // 2 - 1), outline=renk, width=w)
    d.ellipse((c * 0.27, w // 2, c * 0.73, c - w // 2 - 1), outline=renk, width=w)   # boylam
    d.line((c / 2, w, c / 2, c - w), fill=renk, width=w)
    d.line((w, c / 2, c - w, c / 2), fill=renk, width=w)                              # ekvator
    for y in (0.27, 0.73):                                                            # enlemler
        x = c * 0.5 - (c * 0.5 - w) * (1 - (2 * y - 1) ** 2) ** 0.5 * 0.97
        d.line((x, c * y, c - x, c * y), fill=renk, width=w)
    return im.resize((cap, cap), Image.LANCZOS)


def _imlec_ikon(boy, renk=(30, 30, 30)):
    """Tıklama imleci (ok). Beyaz kenarlı, hafif gölgeli."""
    K = 4
    h = boy * K
    noktalar = [(0, 0), (0, 0.78), (0.2, 0.6), (0.34, 0.92), (0.47, 0.86), (0.33, 0.55), (0.58, 0.55)]
    pay = int(h * 0.12)
    im = Image.new("RGBA", (int(h * 0.62) + 2 * pay, h + 2 * pay), (0, 0, 0, 0))
    p = [(pay + x * h, pay + y * h) for x, y in noktalar]
    golge = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(golge).polygon([(x + h * 0.05, y + h * 0.06) for x, y in p], fill=(0, 0, 0, 90))
    im = Image.alpha_composite(im, golge.filter(ImageFilter.GaussianBlur(h * 0.03)))
    d = ImageDraw.Draw(im)
    d.polygon(p, fill=renk, outline=(255, 255, 255), width=int(h * 0.06))
    return im.resize((im.width // K, im.height // K), Image.LANCZOS)


def site_etiketi(img, alt=70, boyut=38):
    """Görselin alt ortasına beyaz zemin üzerine 🌐 morro.com.tr yazar; sağına tıklama imleci koyar."""
    katman = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(katman)
    f = _font(boyut)
    tb = d.textbbox((0, 0), SITE, font=f)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    ikon = _dunya_ikon(int(th * 1.15), (*A.ETIKET_RENK, 255))
    ara = int(boyut * 0.35)
    px, py = 30, 18
    gen = ikon.width + ara + tw + 2 * px
    yuk = th + 2 * py
    x = (img.width - gen) // 2
    y = img.height - alt - yuk
    d.rounded_rectangle((x, y, x + gen, y + yuk), radius=yuk // 2, fill=(255, 255, 255, 235))
    katman.paste(ikon, (x + px, y + (yuk - ikon.height) // 2), ikon)
    d.text((x + px + ikon.width + ara - tb[0], y + py - tb[1]), SITE, font=f, fill=(*A.ETIKET_RENK, 255))
    imlec = _imlec_ikon(int(yuk * 0.95))
    katman.paste(imlec, (x + gen - int(imlec.width * 0.55), y + int(yuk * 0.45)), imlec)
    img.paste(katman, (0, 0), katman)
    return img


def hazirla(kaynak: Image.Image, etiket: str, cikti: Path):
    W, H = A.GENISLIK, A.YUKSEKLIK
    # Arka plan: görselin bulanık ve açık hali (boşluklar beyaz şerit gibi durmasın)
    arka = ImageOps.fit(kaynak, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(40))
    arka = Image.blend(arka, Image.new("RGB", (W, H), (255, 255, 255)), 0.55)
    # Ürün görseli: kesmeden sığdır
    on = ImageOps.contain(kaynak, (W, H), Image.LANCZOS)
    arka.paste(on, ((W - on.width) // 2, (H - on.height) // 2))

    if not etiket:  # 2. ve sonraki fotoğraflar etiketsiz
        cikti.parent.mkdir(parents=True, exist_ok=True)
        arka.save(cikti, "JPEG", quality=90, optimize=True)
        return cikti

    if etiket == A.MARKA_ETIKET and LOGO.exists():
        _logo_yapistir(arka)
        cikti.parent.mkdir(parents=True, exist_ok=True)
        arka.save(cikti, "JPEG", quality=90, optimize=True)
        return cikti

    d = ImageDraw.Draw(arka)
    f = _font(58 if len(etiket) <= 14 else 46)
    x0, y0 = 48, 56
    tb = d.textbbox((0, 0), etiket, font=f)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    px, py = 34, 22
    kutu = (x0, y0, x0 + tw + 2 * px, y0 + th + 2 * py)
    # hafif gölge
    golge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(golge).rounded_rectangle(
        (kutu[0] + 4, kutu[1] + 6, kutu[2] + 4, kutu[3] + 6), radius=26, fill=(0, 0, 0, 70))
    golge = golge.filter(ImageFilter.GaussianBlur(6))
    arka.paste(golge, (0, 0), golge)
    d = ImageDraw.Draw(arka)
    d.rounded_rectangle(kutu, radius=26, fill=A.ETIKET_RENK)
    d.text((x0 + px - tb[0], y0 + py - tb[1]), etiket, font=f, fill=(255, 255, 255))

    cikti.parent.mkdir(parents=True, exist_ok=True)
    arka.save(cikti, "JPEG", quality=90, optimize=True)
    return cikti


def etiket_metni(fiyat, liste_fiyat):
    if liste_fiyat and liste_fiyat > fiyat:
        yuzde = round((1 - fiyat / liste_fiyat) * 100)
        if yuzde >= A.MIN_INDIRIM:
            return f"%{yuzde} İNDİRİM", yuzde
    return A.MARKA_ETIKET, 0


def hikaye(kaynak: Image.Image, baslik, detaylar, cikti: Path):
    """1080x1920 Instagram hikayesi: ürün, özellikleri ve mağaza yönlendirmesi (fiyat yok)."""
    W, H = 1080, 1920
    kaynak = kaynak.convert("RGB")
    arka = ImageOps.fit(kaynak, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(45))
    arka = Image.blend(arka, Image.new("RGB", (W, H), (255, 255, 255)), 0.45)
    on = ImageOps.contain(kaynak, (W - 120, 1120), Image.LANCZOS)
    x, y = (W - on.width) // 2, 210
    golge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(golge).rounded_rectangle((x + 8, y + 14, x + on.width + 8, y + on.height + 14),
                                            radius=30, fill=(0, 0, 0, 80))
    arka.paste(golge.filter(ImageFilter.GaussianBlur(14)), (0, 0), golge.filter(ImageFilter.GaussianBlur(14)))
    maske = Image.new("L", on.size, 0)
    ImageDraw.Draw(maske).rounded_rectangle((0, 0, on.width - 1, on.height - 1), radius=30, fill=255)
    arka.paste(on, (x, y), maske)
    d = ImageDraw.Draw(arka)

    # üstte marka
    if LOGO.exists():
        _logo_yapistir(arka, ortala=True)
    else:
        f = _font(64)
        tb = d.textbbox((0, 0), A.MARKA_ETIKET, font=f)
        d.text(((W - (tb[2] - tb[0])) // 2, 90), A.MARKA_ETIKET, font=f, fill=(40, 40, 40))

    # altta özellik kartı (fiyat yok)
    satirlar = [f"{ad}: {deger}" for _, ad, deger in detaylar[:4]]
    kart_y = y + on.height + 40
    fa = _font(40)
    fd = _font(34, kalin=False)
    yuk = 90 + 52 * len(satirlar) + 70
    d.rounded_rectangle((60, kart_y, W - 60, min(kart_y + yuk, H - 60)), radius=36, fill=(255, 255, 255))
    ad = baslik if len(baslik) <= 40 else baslik[:38].rsplit(" ", 1)[0] + "…"
    tb = d.textbbox((0, 0), ad, font=fa)
    d.text(((W - (tb[2] - tb[0])) // 2, kart_y + 28), ad, font=fa, fill=A.ETIKET_RENK)
    yy = kart_y + 95
    for sat in satirlar:
        if len(sat) > 46:
            sat = sat[:45] + "…"
        tb = d.textbbox((0, 0), sat, font=fd)
        d.text(((W - (tb[2] - tb[0])) // 2, yy), sat, font=fd, fill=(60, 60, 60))
        yy += 52
    alt = "Trendyol'da ve morro.com.tr'de · Link profilde"
    fs = _font(30, kalin=False)
    tb = d.textbbox((0, 0), alt, font=fs)
    d.text(((W - (tb[2] - tb[0])) // 2, min(yy + 12, H - 100)), alt, font=fs, fill=(120, 120, 120))

    cikti.parent.mkdir(parents=True, exist_ok=True)
    arka.save(cikti, "JPEG", quality=90, optimize=True)
    return cikti
