"""Ürün fotoğraflarından Instagram Reels videosu üretir (ücretsiz, yerel).

Akış (dikey 1080x1920, 30 fps, ~12-16 sn):
  1. Açılış: Morro logosu + ürün adı
  2. Ürün fotoğrafları: yavaş yakınlaşma/kayma, yumuşak geçiş
  3. Bilgi kartı: renk, beden, kumaş içeriği (fiyat yok)
  4. Kapanış: "Trendyol'da ve morro.com.tr'de · Link profilde"
Fon müziği muzik.py ile her videoda farklı tarzda üretilir (sakin, telifsiz).
"""
import math
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

import ayarlar as A
import gorsel
import muzik

W, H, FPS = 1080, 1920, 30
MOR = A.ETIKET_RENK
GECIS = 0.45  # sahneler arası geçiş (sn)
PAY_UST, PAY_ALT, PAY_YAN = 0, 0, 0  # kampanya çerçevesi açıkken içerik bu boşluklardan kaçar

# Kasım teması renkleri
BORDO, TURUNCU, ALTIN = (112, 22, 44), (205, 95, 30), (240, 190, 90)
YAPRAK_RENK = [(196, 78, 22), (228, 132, 34), (150, 32, 40), (236, 176, 60), (176, 60, 28)]


def kampanya_aktif(tarih=None):
    k = getattr(A, "KAMPANYA", None)
    if not k:
        return None
    if tarih is None:
        import durum
        tarih = durum.bugun()
    return k if k["baslangic"] <= tarih <= k["bitis"] else None


# --- yardımcılar -----------------------------------------------------------

def _yumusak(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _arka(img):
    """Fotoğrafın bulanık, açık tonlu dikey arka planı."""
    a = ImageOps.fit(img, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(50))
    return Image.blend(a, Image.new("RGB", (W, H), (255, 255, 255)), 0.5)


def _sar(metin, font, genislik, d, en_fazla=3):
    kelimeler, satirlar, sat = metin.split(), [], ""
    for k in kelimeler:
        dene = (sat + " " + k).strip()
        if d.textlength(dene, font=font) <= genislik:
            sat = dene
        else:
            if sat:
                satirlar.append(sat)
            sat = k
    if sat:
        satirlar.append(sat)
    if len(satirlar) > en_fazla:
        satirlar = satirlar[:en_fazla]
        satirlar[-1] = satirlar[-1].rstrip(",.") + "…"
    return satirlar


def _logo(genislik):
    logo = Image.open(gorsel.LOGO).convert("RGBA")
    return ImageOps.contain(logo, (genislik, genislik), Image.LANCZOS)


def kisa_ad(baslik, en_fazla=60):
    b = " ".join(baslik.split())
    return b if len(b) <= en_fazla else b[:en_fazla].rsplit(" ", 1)[0] + "…"


def _katman(boyut):
    return Image.new("RGBA", boyut, (0, 0, 0, 0))


# --- sahneler: her biri t (0..sure) -> RGB kare döndüren fonksiyon ---------

def sahne_acilis(ilk, baslik, sure):
    arka = _arka(ilk)
    # ürünün bulanık olmayan küçük hali ortada, gölgeli
    urun = ImageOps.contain(ilk, (760, 900), Image.LANCZOS)
    logo = _logo(560)
    f = gorsel._font(56)
    d0 = ImageDraw.Draw(arka)
    satirlar = _sar(kisa_ad(baslik, 70), f, W - 160, d0)

    def kare(t):
        img = arka.copy()
        g = _yumusak(t / 0.8)
        # logo kutusu yukarıdan iner
        ust = _katman((W, H))
        du = ImageDraw.Draw(ust)
        kx, ky = (W - logo.width - 80) // 2, int(max(150, PAY_UST + 60) - 60 * (1 - g))
        du.rounded_rectangle((kx, ky, kx + logo.width + 80, ky + logo.height + 60),
                             radius=34, fill=(255, 255, 255, int(240 * g)))
        lg = logo.copy()
        lg.putalpha(lg.getchannel("A").point(lambda a: int(a * g)))
        ust.paste(lg, (kx + 40, ky + 30), lg)
        img.paste(ust, (0, 0), ust)
        # ürün ortada hafif büyüyerek belirir
        s = 0.92 + 0.08 * _yumusak(t / sure)
        u = urun.resize((int(urun.width * s), int(urun.height * s)), Image.BILINEAR)
        ux, uy = (W - u.width) // 2, 520 + (900 - u.height) // 2
        gol = _katman((W, H))
        ImageDraw.Draw(gol).rounded_rectangle((ux + 10, uy + 18, ux + u.width + 10, uy + u.height + 18),
                                              radius=28, fill=(0, 0, 0, int(70 * g)))
        img.paste(gol.filter(ImageFilter.GaussianBlur(16)), (0, 0), gol.filter(ImageFilter.GaussianBlur(16)))
        m = Image.new("L", u.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, u.width - 1, u.height - 1), radius=28, fill=int(255 * g))
        img.paste(u, (ux, uy), m)
        # ürün adı alttan kayarak gelir
        g2 = _yumusak((t - 0.35) / 0.7)
        if g2 > 0:
            yaz = _katman((W, H))
            dy = ImageDraw.Draw(yaz)
            y = int(min(1500, H - PAY_ALT - 290) + 40 * (1 - g2))
            for sat in satirlar:
                tw = dy.textlength(sat, font=f)
                dy.text(((W - tw) / 2, y), sat, font=f, fill=(*MOR, int(255 * g2)))
                y += 74
            img.paste(yaz, (0, 0), yaz)
        return img
    return kare


def sahne_foto(img, sure, yon, alt_yazi=None):
    """Fotoğraf tam genişlikte; yavaş yakınlaşma ve hafif kayma (Ken Burns)."""
    arka = _arka(img)
    alan_h = H - 240 if not PAY_UST else H - PAY_UST - PAY_ALT - 60
    on = ImageOps.contain(img, (W - 2 * PAY_YAN, alan_h), Image.LANCZOS)
    merkez_y = H / 2 - 40 if not PAY_UST else PAY_UST + 30 + alan_h / 2
    f = gorsel._font(40, kalin=False)

    def kare(t):
        p = _yumusak(t / sure) * 0.6 + (t / sure) * 0.4
        s = 1.0 + 0.09 * (p if yon % 2 == 0 else 1 - p)
        u = on.resize((int(on.width * s), int(on.height * s)), Image.BILINEAR)
        kay = int((-1 if yon % 4 < 2 else 1) * 30 * (p - 0.5))
        x, y = (W - u.width) // 2 + kay, int(merkez_y - u.height / 2)
        kare_img = arka.copy()
        kare_img.paste(u, (x, y))
        if alt_yazi:
            g = _yumusak((t - 0.2) / 0.5)
            yaz = _katman((W, H))
            dy = ImageDraw.Draw(yaz)
            tw = dy.textlength(alt_yazi, font=f)
            bx, by = (W - tw) / 2 - 36, H - max(210, PAY_ALT + 120)
            dy.rounded_rectangle((bx, by, bx + tw + 72, by + 76), radius=38,
                                 fill=(*MOR, int(225 * g)))
            dy.text((bx + 36, by + 14), alt_yazi, font=f, fill=(255, 255, 255, int(255 * g)))
            kare_img.paste(yaz, (0, 0), yaz)
        gorsel.site_etiketi(kare_img, alt=max(48, PAY_ALT + 30))
        return kare_img
    return kare


def sahne_bilgi(img, baslik, detaylar, sure):
    arka = _arka(img)
    fb = gorsel._font(52)
    fa = gorsel._font(46)
    fd = gorsel._font(42, kalin=False)
    d0 = ImageDraw.Draw(arka)
    bas = _sar(kisa_ad(baslik, 80), fb, W - 260, d0, en_fazla=2)
    satirlar = []
    for ad, deger in detaylar[:5]:
        deger_sat = _sar(str(deger), fd, W - 300, d0, en_fazla=2)
        satirlar.append((ad, deger_sat))

    def kare(t):
        im = arka.copy()
        k = _katman((W, H))
        dk = ImageDraw.Draw(k)
        g = _yumusak(t / 0.6)
        yuk = 150 + 66 * len(bas) + sum(64 + 54 * len(v) for _, v in satirlar) + 40
        ust = (H - yuk) // 2 - 40 + int(80 * (1 - g))
        dk.rounded_rectangle((80, ust, W - 80, ust + yuk), radius=44, fill=(255, 255, 255, int(245 * g)))
        y = ust + 60
        for sat in bas:
            tw = dk.textlength(sat, font=fb)
            dk.text(((W - tw) / 2, y), sat, font=fb, fill=(*MOR, int(255 * g)))
            y += 66
        y += 40
        for i, (ad, vals) in enumerate(satirlar):
            gi = _yumusak((t - 0.35 - 0.18 * i) / 0.45)
            if gi <= 0:
                break
            a = int(255 * gi)
            dx = int(30 * (1 - gi))
            dk.ellipse((150 + dx, y + 20, 172 + dx, y + 42), fill=(*MOR, a))
            dk.text((195 + dx, y), ad, font=fa, fill=(40, 40, 40, a))
            y += 62
            for v in vals:
                dk.text((195 + dx, y), v, font=fd, fill=(90, 90, 90, a))
                y += 54
            y += 4
        im.paste(k, (0, 0), k)
        gorsel.site_etiketi(im, alt=max(48, PAY_ALT + 30))
        return im
    return kare


def sahne_kapanis(sure, site=False):
    logo = _logo(620)
    f1 = gorsel._font(64)
    f2 = gorsel._font(44, kalin=False)

    zemin = _gradyan(W, H, BORDO, TURUNCU) if site else Image.new("RGB", (W, H), MOR)
    yap = Yapraklar(10, kenar=False, tohum=5) if site else None

    def kare(t):
        im = zemin.copy()
        if yap:
            yap.ciz(im, t + 3.0)
        # hafif renk geçişi
        k = _katman((W, H))
        dk = ImageDraw.Draw(k)
        g = _yumusak(t / 0.7)
        s = 0.9 + 0.1 * g
        lg = logo.resize((int(logo.width * s), int(logo.height * s)), Image.LANCZOS)
        kx = (W - lg.width - 100) // 2
        ky = 620
        dk.rounded_rectangle((kx, ky, kx + lg.width + 100, ky + lg.height + 80), radius=40,
                             fill=(255, 255, 255, int(255 * g)))
        lg.putalpha(lg.getchannel("A").point(lambda a: int(a * g)))
        k.paste(lg, (kx + 50, ky + 40), lg)
        g2 = _yumusak((t - 0.4) / 0.6)
        y = ky + lg.height + 160 + int(30 * (1 - g2))
        metinler = [("Trendyol'da ve", f1, (255, 255, 255)), ("morro.com.tr'de", f1, (255, 255, 255))]
        metinler.append(("Link profilde", f2, (235, 215, 230)))
        for metin, font, renk in metinler:
            tw = dk.textlength(metin, font=font)
            dk.text(((W - tw) / 2, y), metin, font=font, fill=(*renk, int(255 * g2)))
            y += 96
        im.paste(k, (0, 0), k)
        if g2 > 0:  # tıklanabilir site etiketi (büyük)
            et = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gorsel.site_etiketi(et, alt=H - y - 150, boyut=56)
            et.putalpha(et.getchannel("A").point(lambda a: int(a * g2)))
            im.paste(et, (0, 0), et)
        return im
    return kare


# --- Kasım teması ----------------------------------------------------------

def _gradyan(w, h, ust, alt, yatay=False):
    n = w if yatay else h
    t = np.linspace(0, 1, n)[:, None]
    renk = (np.array(ust)[None, :] * (1 - t) + np.array(alt)[None, :] * t).astype(np.uint8)
    if yatay:
        dizi = np.broadcast_to(renk[None, :, :], (h, w, 3))
    else:
        dizi = np.broadcast_to(renk[:, None, :], (h, w, 3))
    return Image.fromarray(np.ascontiguousarray(dizi), "RGB")


def _yaprak(renk, boyut=120):
    """Sonbahar yaprağı: sivri uçlu oval gövde, sap ve damarlar."""
    im = _katman((boyut, boyut))
    d = ImageDraw.Draw(im)
    c = boyut / 2
    uzun, gen = boyut * 0.40, boyut * 0.22
    ust, alt = [], []
    for k in range(25):  # sivri uçlu oval (badem/yaprak)
        u = k / 24
        x = c - uzun + 2 * uzun * u
        y = gen * math.sin(math.pi * u) ** 0.8
        ust.append((x, c - y))
        alt.append((x, c + y))
    d.polygon(ust + alt[::-1], fill=(*renk, 240))
    koyu = tuple(int(x * 0.65) for x in renk)
    gw = max(2, boyut // 40)
    d.line((c - uzun - boyut * 0.08, c, c + uzun * 0.9, c), fill=(*koyu, 255), width=gw)  # sap + orta damar
    for k in range(1, 5):
        x = c - uzun + 2 * uzun * k / 5
        h = gen * math.sin(math.pi * k / 5) ** 0.8 * 0.8
        d.line((x, c, x + uzun * 0.22, c - h), fill=(*koyu, 200), width=max(1, gw - 1))
        d.line((x, c, x + uzun * 0.22, c + h), fill=(*koyu, 200), width=max(1, gw - 1))
    return im


class Yapraklar:
    """Ekranda süzülerek düşen yapraklar. kenar=True ise sadece kenarlarda/şeritlerde."""

    def __init__(self, adet, kenar=True, tohum=3):
        rng = np.random.default_rng(tohum)
        self.ler = []
        for i in range(adet):
            boy = int(rng.uniform(42, 78))
            sprite = _yaprak(YAPRAK_RENK[i % len(YAPRAK_RENK)], 120).resize((boy, boy), Image.LANCZOS)
            if kenar:
                x = rng.uniform(-10, 70) if i % 2 == 0 else rng.uniform(W - 80, W)
            else:
                x = rng.uniform(0, W)
            self.ler.append(dict(s=sprite, x=x, y0=rng.uniform(-200, H), hiz=rng.uniform(90, 170),
                                 sal=rng.uniform(15, 40), faz=rng.uniform(0, 6.28),
                                 don=rng.uniform(-60, 60), a0=rng.uniform(0, 360)))

    def ciz(self, img, t):
        for y in self.ler:
            yy = (y["y0"] + y["hiz"] * t) % (H + 200) - 100
            xx = y["x"] + y["sal"] * math.sin(t * 1.6 + y["faz"])
            s = y["s"].rotate(y["a0"] + y["don"] * t, resample=Image.BILINEAR, expand=True)
            img.paste(s, (int(xx - s.width / 2), int(yy - s.height / 2)), s)
        return img


def cerceve_olustur(k):
    """Kasım çerçevesi: üstte kampanya şeridi, altta geçerlilik şeridi, yanlarda ince kenar."""
    ust_h, alt_h, yan = 230, 150, 14
    katman = _katman((W, H))
    ust = _gradyan(W, ust_h, BORDO, TURUNCU, yatay=True)
    alt = _gradyan(W, alt_h, TURUNCU, BORDO, yatay=True)
    katman.paste(ust, (0, 0))
    katman.paste(alt, (0, H - alt_h))
    kenar = _gradyan(yan, H, BORDO, TURUNCU)
    katman.paste(kenar, (0, 0))
    katman.paste(kenar, (W - yan, 0))
    d = ImageDraw.Draw(katman)
    d.line((0, ust_h - 4, W, ust_h - 4), fill=(*ALTIN, 255), width=4)
    d.line((0, H - alt_h + 2, W, H - alt_h + 2), fill=(*ALTIN, 255), width=4)
    f1, f0, f2 = gorsel._font(108), gorsel._font(38), gorsel._font(44)
    tw = d.textlength(k["ust_kucuk"], font=f0)
    d.text(((W - tw) / 2, 16), k["ust_kucuk"], font=f0, fill=(*ALTIN, 255))
    tw = d.textlength(k["ust"], font=f1, )
    d.text(((W - tw) / 2, 58), k["ust"], font=f1, fill=(255, 255, 255, 255),
           stroke_width=4, stroke_fill=(*ALTIN, 255))
    tw = d.textlength(k["alt"], font=f2)
    d.text(((W - tw) / 2, H - alt_h + (alt_h - 52) / 2), k["alt"], font=f2, fill=(255, 255, 255, 255))
    return katman, ust_h, alt_h, yan


def rozet_olustur(k, cap=290):
    """Yıldız kenarlı altın rozet: '4 AL / 3 ÖDE'."""
    im = _katman((cap, cap))
    d = ImageDraw.Draw(im)
    c = cap / 2
    noktalar = []
    for i in range(48):
        aci = i * math.pi / 24
        r = c * (0.98 if i % 2 == 0 else 0.88)
        noktalar.append((c + r * math.cos(aci), c + r * math.sin(aci)))
    d.polygon(noktalar, fill=(*ALTIN, 255))
    d.ellipse((c * 0.22, c * 0.22, cap - c * 0.22, cap - c * 0.22), fill=(*BORDO, 255),
              outline=(255, 255, 255, 255), width=4)
    f1, f2 = gorsel._font(int(cap * 0.24)), gorsel._font(int(cap * 0.075))
    for metin, font, y, renk in ((k["buyuk1"], f1, c - cap * 0.22, (255, 255, 255)),
                                 (k["buyuk2"], f1, c - cap * 0.02, (255, 255, 255)),
                                 (k["ust_kucuk"], f2, c + cap * 0.22, ALTIN)):
        tb = d.textbbox((0, 0), metin, font=font)
        d.text((c - (tb[2] - tb[0]) / 2 - tb[0], y - tb[1] + 4), metin, font=font, fill=(*renk, 255))
    return im


def rozet_ciz(img, rozet, t):
    """Sağ üst köşede hafifçe nabız gibi atan rozet."""
    s = 1.0 + 0.07 * math.sin(t * 2 * math.pi * 1.1)
    r = rozet.resize((int(rozet.width * s), int(rozet.height * s)), Image.BILINEAR)
    r = r.rotate(-12 + 4 * math.sin(t * 1.3), resample=Image.BILINEAR, expand=True)
    cx, cy = W - PAY_YAN - 30 - rozet.width // 2, PAY_UST + 20 + rozet.height // 2
    img.paste(r, (cx - r.width // 2, cy - r.height // 2), r)
    return img


def sahne_kampanya(k, sure):
    """Tam ekran kampanya duyurusu: büyük '4 AL 3 ÖDE'."""
    arka = _gradyan(W, H, BORDO, TURUNCU)
    yap = Yapraklar(16, kenar=False, tohum=11)
    fb = gorsel._font(250)
    fk = gorsel._font(54)
    fs = gorsel._font(46, kalin=False)

    hiz = max(1.0, 3.0 / sure)  # kısa sürümde animasyonlar daha hızlı

    def kare(t):
        t = t * hiz
        im = arka.copy()
        yap.ciz(im, t + 1.0)
        k1 = _katman((W, H))
        d = ImageDraw.Draw(k1)
        g0 = _yumusak(t / 0.5)
        tw = d.textlength(k["ust_kucuk"], font=fk)
        d.text(((W - tw) / 2, 470), k["ust_kucuk"], font=fk, fill=(*ALTIN, int(255 * g0)))
        im.paste(k1, (0, 0), k1)
        for i, (metin, y) in enumerate(((k["buyuk1"], 660), (k["buyuk2"], 960))):
            g = _yumusak((t - 0.25 - 0.3 * i) / 0.45)
            if g <= 0:
                continue
            s = 0.6 + 0.4 * g + 0.05 * math.sin(max(0, t - 1.2) * 4) * (1 if t > 1.2 else 0)
            tb = ImageDraw.Draw(im).textbbox((0, 0), metin, font=fb)
            yazi = _katman((tb[2] + 40, tb[3] + 40))
            ImageDraw.Draw(yazi).text((20, 20), metin, font=fb, fill=(255, 255, 255, 255),
                                      stroke_width=6, stroke_fill=(*ALTIN, 255))
            yazi = yazi.resize((int(yazi.width * s), int(yazi.height * s)), Image.BILINEAR)
            yazi.putalpha(yazi.getchannel("A").point(lambda a: int(a * g)))
            im.paste(yazi, ((W - yazi.width) // 2, int(y + 150 - yazi.height / 2)), yazi)
        k2 = _katman((W, H))
        d = ImageDraw.Draw(k2)
        g3 = _yumusak((t - 1.0) / 0.5)
        y = 1370 + int(30 * (1 - g3))
        for metin, font, renk in ((k["alt_satir1"], fk, (255, 255, 255)),
                                  (k["alt_satir2"], fs, (250, 225, 200))):
            tw = d.textlength(metin, font=font)
            if metin is k["alt_satir1"]:
                d.rounded_rectangle(((W - tw) / 2 - 40, y - 14, (W + tw) / 2 + 40, y + 80), radius=46,
                                    fill=(255, 255, 255, int(40 * g3)), outline=(*ALTIN, int(255 * g3)), width=3)
            d.text(((W - tw) / 2, y), metin, font=font, fill=(*renk, int(255 * g3)))
            y += 130
        im.paste(k2, (0, 0), k2)
        return im
    return kare


# --- birleştirme -----------------------------------------------------------

def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


BEDEN_SIRA = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "XXL", "3XL", "XXXL", "4XL", "5XL", "6XL"]


def beden_sirala(metin):
    bedenler = [b.strip() for b in metin.split(",") if b.strip()]
    def anahtar(b):
        u = b.upper()
        if u in BEDEN_SIRA:
            return (0, BEDEN_SIRA.index(u), u)
        rakam = "".join(c for c in u if c.isdigit())
        return (1, int(rakam) if rakam else 999, u)
    return sorted(bedenler, key=anahtar)


def uret(fotolar, baslik, detaylar, cikti, muzikli=True, tarih=None, tohum=None):
    """fotolar: yerel dosya yolları. detaylar: [(ad, değer), ...]. Video yolunu döndürür."""
    global PAY_UST, PAY_ALT, PAY_YAN
    kamp = kampanya_aktif(tarih)
    cerceve = yapraklar = None
    if kamp:
        cerceve, PAY_UST, PAY_ALT, PAY_YAN = cerceve_olustur(kamp)
        yapraklar = Yapraklar(8, kenar=True)
        rozet = rozet_olustur(kamp)
    else:
        PAY_UST = PAY_ALT = PAY_YAN = 0
    resimler = [gorsel.ac(p) for p in fotolar if Path(p).exists()][:A.FOTO_SAYISI]
    if not resimler:
        raise RuntimeError("Reels için fotoğraf yok")
    foto_sure = 4.0 if len(resimler) == 1 else (3.0 if len(resimler) == 2 else 2.4)
    detaylar = [(a, ", ".join(beden_sirala(v)) if a == "Beden" else v) for a, v in detaylar]
    renk = next((v for a, v in detaylar if a == "Renk"), None)
    bedenler = beden_sirala(next((v for a, v in detaylar if a == "Beden"), ""))
    beden = (f"{bedenler[0]}–{bedenler[-1]}" if len(bedenler) > 1 else
             (bedenler[0] if bedenler else None))
    alt = " · ".join(x for x in (renk and renk.split(",")[0].strip(), beden) if x)
    sahneler = []
    if kamp:  # video kampanya duyurusuyla açılır (ilk saniyeler en çok izlenen kısım)
        sahneler.append((sahne_kampanya(kamp, 2.4), 2.4))
    ilk_cerceveli = len(sahneler)
    sahneler.append((sahne_acilis(resimler[0], baslik, 2.6), 2.6))
    for i, r in enumerate(resimler):
        sahneler.append((sahne_foto(r, foto_sure, i, alt_yazi=alt if i == 0 and alt else None), foto_sure))
    if detaylar:
        sahneler.append((sahne_bilgi(resimler[min(1, len(resimler) - 1)], baslik, detaylar, 3.6), 3.6))
    cerceveli = len(sahneler)  # bu sıraya kadar olan sahneler çerçeveli
    if kamp:
        sahneler.append((sahne_kampanya(kamp, 3.0), 3.0))
    sahneler.append((sahne_kapanis(2.6, site=bool(kamp)), 2.6))

    # zaman çizelgesi (geçişler üst üste biner)
    baslangic, t0 = [], 0.0
    for _, s in sahneler:
        baslangic.append(t0)
        t0 += s - GECIS
    toplam = t0 + GECIS
    cikti = Path(cikti)
    cikti.parent.mkdir(parents=True, exist_ok=True)
    ses_yol = cikti.with_suffix(".wav")
    if muzikli:
        uret.son_tarz = muzik.uret(toplam + 0.1, ses_yol, tohum if tohum is not None else str(cikti))

    komut = [_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if muzikli:
        komut += ["-i", str(ses_yol), "-c:a", "aac", "-b:a", "128k", "-shortest"]
    komut += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
              "-profile:v", "high", "-movflags", "+faststart", str(cikti)]
    def sus(i, kare, t):  # çerçeveli sahnelere çerçeve, yaprak ve rozet ekle
        if cerceve is not None and ilk_cerceveli <= i < cerceveli:
            kare.paste(cerceve, (0, 0), cerceve)
            yapraklar.ciz(kare, t)
            if i > ilk_cerceveli:  # açılışta logo var, rozet fotoğraflardan itibaren
                rozet_ciz(kare, rozet, t)
        return kare

    p = subprocess.Popen(komut, stdin=subprocess.PIPE)
    try:
        for f in range(int(math.ceil(toplam * FPS))):
            t = f / FPS
            etkin = [(i, t - baslangic[i]) for i, (_, s) in enumerate(sahneler)
                     if baslangic[i] <= t < baslangic[i] + s]
            if not etkin:
                etkin = [(len(sahneler) - 1, sahneler[-1][1] - 0.001)]
            i, yerel = etkin[-1]
            kare = sahneler[i][0](yerel)
            if len(etkin) > 1:  # geçiş: önceki sahneyle karıştır
                j, yj = etkin[0]
                oran = _yumusak(yerel / GECIS)
                onceki = sus(j, sahneler[j][0](yj), t)
                kare = Image.blend(onceki, sus(i, kare, t), oran)
            else:
                kare = sus(i, kare, t)
            p.stdin.write(kare.tobytes())
        p.stdin.close()
        if p.wait() != 0:
            raise RuntimeError("ffmpeg video oluşturamadı")
    finally:
        if p.poll() is None:
            p.kill()
        ses_yol.unlink(missing_ok=True)
    return cikti, toplam


def detaylari_ayikla(aciklama):
    """Plandaki açıklamanın 'Ürün özellikleri' bölümünden (ad, değer) listesi."""
    out, icinde = [], False
    for sat in (aciklama or "").splitlines():
        if "Ürün özellikleri" in sat:
            icinde = True
            continue
        if icinde:
            if not sat.strip():
                break
            if ":" in sat:
                ad, deger = sat.split(":", 1)
                ad = ad.split(" ", 1)[-1].strip() if " " in ad.strip() else ad.strip()
                deger = deger.strip()
                if deger and deger.lower() != "belirtilmemiş":
                    out.append((ad, deger))
    return out
