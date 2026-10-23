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


def _logo_yapistir(arka):
    """logo.png varsa sol üst köşeye beyaz zemin üzerinde logoyu koyar."""
    logo = Image.open(LOGO).convert("RGBA")
    logo = ImageOps.contain(logo, (300, 120), Image.LANCZOS)
    px, py, x0, y0 = 28, 20, 48, 56
    kutu = Image.new("RGBA", (logo.width + 2 * px, logo.height + 2 * py), (0, 0, 0, 0))
    ImageDraw.Draw(kutu).rounded_rectangle((0, 0, kutu.width - 1, kutu.height - 1),
                                           radius=26, fill=(255, 255, 255, 235))
    kutu.paste(logo, (px, py), logo)
    arka.paste(kutu, (x0, y0), kutu)


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
