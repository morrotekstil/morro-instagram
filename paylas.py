"""Zamanı gelen paylaşımı Instagram'a gönderir.

Her çalıştırmada en fazla 1 gönderi paylaşılır: saati gelmiş (15 dk tolerans)
ve hâlâ "bekliyor" durumundaki ilk kalem. Ürünün stoğu bittiyse yerine
yedek ürün geçer. Plan dosyasında bir kalemin durumunu "iptal" yaparsan
o paylaşım atlanır.
"""
import datetime as dt
import sys
import time
import traceback

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
        if not u or u["stok"] < 1:
            yedek = next((y for y in plan.get("yedekler", []) if y["durum"] == "yedek"
                          and guncel.get(y["urun_id"], {}).get("stok", 0) >= 1), None)
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
            plan["paylasimlar"].append(yedek)
            k = yedek
        elif abs(u["fiyat"] - k["fiyat"]) >= 1:
            print(f"Uyarı: fiyat sabahtan beri değişti ({k['fiyat']} -> {u['fiyat']})")

    if not gorsel_hazir_mi(k["gorsel_url"]):
        raise SystemExit(f"Görsel adresine ulaşılamıyor: {k['gorsel_url']}")

    if A.DRY_RUN:
        print("[DENEME] Paylaşılacaktı:", k["baslik"], k["gorsel_url"])
        print(k["aciklama"])
        return

    mid, link = instagram.paylas(D.token_al(), k["gorsel_url"], k["aciklama"])
    k["durum"] = "paylaşıldı"
    k["paylasim_saati"] = D.simdi().isoformat(timespec="minutes")
    k["media_id"], k["permalink"] = mid, link
    gecmis = D.oku(D.GECMIS, [])
    gecmis.append({
        "tarih": plan["tarih"], "saat": k["saat"], "urun_id": k["urun_id"],
        "baslik": k["baslik"], "fiyat": k["fiyat"], "liste_fiyat": k["liste_fiyat"],
        "media_id": mid, "permalink": link,
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
