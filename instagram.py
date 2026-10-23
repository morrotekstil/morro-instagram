"""Instagram API (Instagram Login) ile gönderi paylaşma ve token yenileme."""
import time

import requests

import ayarlar as A


class IGHata(Exception):
    pass


def _kontrol(r):
    try:
        veri = r.json()
    except ValueError:
        veri = {"ham": r.text[:300]}
    if r.status_code >= 400 or "error" in veri:
        raise IGHata(f"{r.status_code}: {veri}")
    return veri


def _kapsayici(token, veri):
    veri = dict(veri, access_token=token)
    return _kontrol(requests.post(f"{A.IG_API}/{A.IG_USER_ID}/media", data=veri, timeout=60))["id"]


def paylas(token, gorsel_urls, aciklama):
    """Gönderi paylaşır: 1 görsel ise tekli, fazlaysa kaydırmalı (carousel).
    (media_id, permalink) döndürür."""
    if isinstance(gorsel_urls, str):
        gorsel_urls = [gorsel_urls]
    gorsel_urls = gorsel_urls[:10]
    if len(gorsel_urls) == 1:
        kap = _kapsayici(token, {"image_url": gorsel_urls[0], "caption": aciklama})
    else:
        cocuklar = []
        for u in gorsel_urls:
            c = _kapsayici(token, {"image_url": u, "is_carousel_item": "true"})
            _bekle(token, c)
            cocuklar.append(c)
        kap = _kapsayici(token, {"media_type": "CAROUSEL", "children": ",".join(cocuklar),
                                  "caption": aciklama})
    _bekle(token, kap)
    mid = _kontrol(requests.post(f"{A.IG_API}/{A.IG_USER_ID}/media_publish", data={
        "creation_id": kap, "access_token": token}, timeout=60))["id"]
    try:
        link = _kontrol(requests.get(f"{A.IG_API}/{mid}", params={
            "fields": "permalink", "access_token": token}, timeout=30)).get("permalink")
    except IGHata:
        link = None
    return mid, link


def _bekle(token, kap):
    for _ in range(30):
        st = _kontrol(requests.get(f"{A.IG_API}/{kap}", params={
            "fields": "status_code,status", "access_token": token}, timeout=30))
        kod = st.get("status_code")
        if kod == "FINISHED":
            break
        if kod in ("ERROR", "EXPIRED"):
            raise IGHata(f"Görsel işlenemedi: {st}")
        time.sleep(5)
    else:
        raise IGHata("Görsel işleme zaman aşımı")


def yenile(token):
    """Uzun ömürlü token'ı 60 gün daha uzatır, (yeni_token, saniye) döndürür."""
    veri = _kontrol(requests.get("https://graph.instagram.com/refresh_access_token", params={
        "grant_type": "ig_refresh_token", "access_token": token}, timeout=30))
    return veri["access_token"], int(veri.get("expires_in", 0))


def hesap(token):
    """Token'ın hangi hesaba ait olduğunu döndürür (deneme için)."""
    return _kontrol(requests.get(f"{A.IG_API}/me", params={
        "fields": "user_id,username", "access_token": token}, timeout=30))
