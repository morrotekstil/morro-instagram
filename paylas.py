"""Zamanı gelen paylaşımı Instagram'a gönderir.

Her çalıştırmada en fazla 1 gönderi paylaşılır: saati gelmiş (15 dk tolerans)
ve hâlâ "bekliyor" durumundaki ilk kalem. Ürünün stoğu bittiyse yerine
yedek ürün geçer. Plan dosyasında bir kalemin durumunu "iptal" yaparsan
o paylaşım atlanır.
"""
import datetime as dt
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import requests

import ayarlar as A
import durum as D
import instagram
import trendyol


def saati_geldi(saat, simdi, tolerans_dk=15):
    s = dt.datetime.combine(simdi.date(), dt.time.fromisoformat(saat), tzinfo=D.TR)
    return simdi + dt.timedelta(minutes=tolerans_dk) >= s


def gorsel_hazir_mi(url):
    for _ in range(12):
        try:
            if requests.head(url, timeout=20).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(10)
    return False


def yerel_fotolar(k):
    return [D.KOK / ("media/" + u.rsplit("/media/", 1)[1])
            for u in (k.get("gorsel_urls") or [k.get("gorsel_url")]) if u and "/media/" in u]


def reels_uret(k, ref):
    """Kalemin fotoğraflarından Reels videosu üretir (reels/ klasörüne, depoya eklenmez)."""
    import reels
    fotolar = [f for f in yerel_fotolar(k) if f.exists()]
    if not fotolar:
        raise RuntimeError("fotoğraf dosyaları bulunamadı")
    detay = [tuple(x) for x in (k.get("detaylar") or [])] or reels.detaylari_ayikla(k.get("aciklama"))
    ad = ref.replace("#", "-").replace(":", "")
    yol, sure = reels.uret(fotolar, k["baslik"], detay, D.KOK / "reels" / f"{ad}.mp4", tohum=ref)
    print(f"Reels hazır: {yol.name} ({sure:.1f} sn, müzik: {getattr(reels.uret, 'son_tarz', '?')})")
    return yol


def video_adresi_al(yol):
    """Doğrudan yükleme olmazsa: videoyu 'videolar' dalına (tek dosya, geçmiş tutulmaz) koyup
    herkese açık adresini döndürür."""
    def al():
        ad = Path(yol).name
        git = lambda *a, girdi=None: subprocess.run(["git", *a], cwd=D.KOK, input=girdi, text=True,
                                                     capture_output=True, check=True).stdout.strip()
        blob = git("hash-object", "-w", str(yol))
        agac = git("mktree", girdi=f"100644 blob {blob}\t{ad}\n")
        ortam = dict(os.environ, GIT_AUTHOR_NAME="morro-bot", GIT_COMMITTER_NAME="morro-bot",
                     GIT_AUTHOR_EMAIL="actions@users.noreply.github.com",
                     GIT_COMMITTER_EMAIL="actions@users.noreply.github.com")
        commit = subprocess.run(["git", "commit-tree", agac, "-m", f"Video {ad}"], cwd=D.KOK, env=ortam,
                                text=True, capture_output=True, check=True).stdout.strip()
        git("push", "-f", "origin", f"{commit}:refs/heads/videolar")
        url = f"https://raw.githubusercontent.com/{A.REPO}/videolar/{ad}"
        if not gorsel_hazir_mi(url):
            raise RuntimeError("video adresine ulaşılamıyor")
        return url
    return al


def main():
    zorla = "--simdi" in sys.argv  # elle çalıştırmada saati bekleme
    plan_yol = D.plan_yolu()
    plan = D.oku(plan_yol, None)
    if not plan:
        print("Bugün için plan yok, çıkılıyor.")
        return
    simdi = D.simdi()
    if not zorla:  # saatinin üzerinden 90 dk geçmiş paylaşımı artık yapma
        for k in plan["paylasimlar"]:
            if k["durum"] == "bekliyor" and saati_geldi(k["saat"], simdi, tolerans_dk=-90):
                k["durum"] = "kaçırıldı (saati geçti)"
    sira = [k for k in plan["paylasimlar"] if k["durum"] == "bekliyor"
            and (zorla or saati_geldi(k["saat"], simdi))]
    if not sira:
        if not A.DRY_RUN:
            D.yaz(plan_yol, plan)
            D.yaz(D.KOK / "plan" / "bugun.json", plan)
        print("Saati gelen paylaşım yok.")
        return
    k = sira[0]

    # Son stok kontrolü
    try:
        guncel = {u["id"]: u for u in trendyol.urunler()}
    except Exception as e:
        print("Stok kontrol edilemedi, plana göre devam:", e)
        guncel = None
    if guncel is not None:
        u = guncel.get(k["urun_id"])
        if k.get("kaynak") == "reels_tekrar" and (not u or u["stok"] < 1):
            k["durum"] = "atlandı (stok yok)"
            if not A.DRY_RUN:
                D.yaz(plan_yol, plan)
                D.yaz(D.KOK / "plan" / "bugun.json", plan)
            print("Tekrar paylaşılacak ürün stokta yok, atlandı.")
            return
        if not u or u["stok"] < 1:
            uygun = [y for y in plan.get("yedekler", []) if y["durum"] == "yedek"
                     and guncel.get(y["urun_id"], {}).get("stok", 0) >= 1]
            # önce aynı gruptan (Morro yerine Morro) yedek
            yedek = next((y for y in uygun if y.get("grup") == k.get("grup")), None) or \
                next(iter(uygun), None)
            if not yedek:
                k["durum"] = "atlandı (stok yok, yedek yok)"
                if not A.DRY_RUN:
                    D.yaz(plan_yol, plan)
                    D.yaz(D.KOK / "plan" / "bugun.json", plan)
                print("Ürün stokta yok ve uygun yedek bulunamadı.")
                return
            print(f"{k['baslik']} stokta yok, yerine yedek: {yedek['baslik']}")
            k["durum"] = "yerine yedek geçti (stok bitti)"
            yedek["durum"] = "bekliyor"
            yedek["saat"] = k["saat"]
            yedek["tur"] = k.get("tur", "gonderi")
            plan["paylasimlar"].append(yedek)
            k = yedek
        elif abs(u["fiyat"] - k["fiyat"]) >= 1:
            print(f"Uyarı: fiyat sabahtan beri değişti ({k['fiyat']} -> {u['fiyat']})")

    sadece_hikaye = k.get("tur") == "hikaye"
    tekrar = k.get("kaynak") == "reels_tekrar"
    urls = [] if sadece_hikaye else (k.get("gorsel_urls") or [k["gorsel_url"]])

    # Reels videosu (gönderiler ve önceki Reels'in hikayede tekrarı için)
    video = None
    if getattr(A, "REELS", False) and (not sadece_hikaye or tekrar):
        try:
            video = reels_uret(k, k.get("kaynak_ref") or f"{plan['tarih']}#{k['saat']}")
        except Exception as e:
            k["reels_hata"] = f"video üretilemedi: {e}"[:200]
            print("Reels üretilemedi, fotoğrafla devam:", e)

    if not video:
        urls_kontrol = [k["hikaye_url"]] if sadece_hikaye else urls
        if sadece_hikaye and not k.get("hikaye_url"):
            raise SystemExit("Hikaye görseli yok")
        for url in urls_kontrol:
            if not gorsel_hazir_mi(url):
                raise SystemExit(f"Görsel adresine ulaşılamıyor: {url}")

    if A.DRY_RUN:
        try:
            print("[DENEME] Instagram token'ı geçerli, hesap:", instagram.hesap(D.token_al()).get("username"))
        except Exception as e:
            print("[DENEME] Instagram token'ı ÇALIŞMIYOR:", e)
        tur = "Reels" if video and not sadece_hikaye else ("video hikaye" if video else
                                                          ("hikaye" if sadece_hikaye else "kaydırmalı gönderi"))
        print(f"[DENEME] {tur} paylaşılacaktı:", k["baslik"], video or urls or k.get("hikaye_url"))
        if not sadece_hikaye:
            print(k["aciklama"])
        return

    token = D.token_al()
    url_al = video_adresi_al(video) if video else None
    mid = link = None
    if sadece_hikaye:
        if video:
            try:
                k["hikaye_id"] = instagram.hikaye_video_paylas(token, video, url_al)
                k["hikaye_video"] = True
            except Exception as e:
                k["reels_hata"] = f"video hikaye: {e}"[:200]
                print("Video hikaye paylaşılamadı, görselle devam:", e)
        if not k.get("hikaye_id"):
            if not gorsel_hazir_mi(k["hikaye_url"]):
                raise SystemExit(f"Görsel adresine ulaşılamıyor: {k['hikaye_url']}")
            k["hikaye_id"] = instagram.hikaye_paylas(token, k["hikaye_url"])
        mid = k["hikaye_id"]
        print("Hikaye paylaşıldı")
    else:
        if video:
            try:
                mid, link = instagram.reels_paylas(token, video, k["aciklama"], url_al)
                k["reels"] = True
                print("Reels paylaşıldı")
            except Exception as e:
                k["reels_hata"] = f"Reels: {e}"[:200]
                print("Reels paylaşılamadı, kaydırmalı gönderiyle devam:", e)
        if not mid:
            for url in urls:
                if not gorsel_hazir_mi(url):
                    raise SystemExit(f"Görsel adresine ulaşılamıyor: {url}")
            mid, link = instagram.paylas(token, urls, k["aciklama"])
        if A.HIKAYE:
            # Gönderinin hikayesi: aynı Reels videosu (olmazsa hazır hikaye görseli)
            try:
                if video and k.get("reels") and getattr(A, "HIKAYE_REELS", False):
                    k["hikaye_id"] = instagram.hikaye_video_paylas(token, video, url_al)
                    k["hikaye_video"] = True
                elif k.get("hikaye_url") and gorsel_hazir_mi(k["hikaye_url"]):
                    k["hikaye_id"] = instagram.hikaye_paylas(token, k["hikaye_url"])
                print("Hikaye paylaşıldı")
            except Exception as e:
                k["hikaye_hata"] = str(e)[:200]
                print("Hikaye paylaşılamadı:", e)
    k["durum"] = "paylaşıldı"
    k["paylasim_saati"] = D.simdi().isoformat(timespec="minutes")
    k["media_id"], k["permalink"] = mid, link
    gecmis = D.oku(D.GECMIS, [])
    if not tekrar:  # hikayede tekrar edilen Reels yeni ürün paylaşımı sayılmaz
        gecmis.append({
            "tarih": plan["tarih"], "saat": k["saat"], "urun_id": k["urun_id"],
            "tur": k.get("tur", "gonderi"), "grup": k.get("grup"), "model": k.get("model"),
            "baslik": k["baslik"], "fiyat": k["fiyat"], "liste_fiyat": k["liste_fiyat"],
            "media_id": mid, "permalink": link, "reels": bool(k.get("reels")),
        })
    D.yaz(D.GECMIS, gecmis)
    D.yaz(plan_yol, plan)
    D.yaz(D.KOK / "plan" / "bugun.json", plan)
    print("Paylaşıldı:", k["baslik"], link)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
