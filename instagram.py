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


def paylas(token, gorsel_url, aciklama):
    """Tek görselli gönderi paylaşır, (media_id, permalink) döndürür."""
    r = requests.post(f"{A.IG_API}/{A.IG_USER_ID}/media", data={
        "image_url": gorsel_url, "caption": aciklama, "access_token": token}, timeout=60)
    kap = _kontrol(r)["id"]
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
    mid = _kontrol(requests.post(f"{A.IG_API}/{A.IG_USER_ID}/media_publish", data={
        "creation_id": kap, "access_token": token}, timeout=60))["id"]
    try:
        link = _kontrol(requests.get(f"{A.IG_API}/{mid}", params={
            "fields": "permalink", "access_token": token}, timeout=30)).get("permalink")
    except IGHata:
        link = None
    return mid, link


def yenile(token):
    """Uzun ömürlü token'ı 60 gün daha uzatır, (yeni_token, saniye) döndürür."""
    veri = _kontrol(requests.get("https://graph.instagram.com/refresh_access_token", params={
        "grant_type": "ig_refresh_token", "access_token": token}, timeout=30))
    return veri["access_token"], int(veri.get("expires_in", 0))
