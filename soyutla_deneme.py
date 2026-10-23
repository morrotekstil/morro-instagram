"""Deneme: stoktaki sütyen/takım ürünlerinden birkaçını soyutlar ve
sonuçları deneme/soyut/ klasörüne yazar (Instagram'a hiçbir şey gitmez)."""
import sys
from pathlib import Path

import gorsel
import plan
import soyutla
import trendyol

KLASOR = Path(__file__).parent / "deneme" / "soyut"
ADET = int(sys.argv[1]) if len(sys.argv) > 1 else 6


def main():
    KLASOR.mkdir(parents=True, exist_ok=True)
    for f in KLASOR.glob("*.jpg"):
        f.unlink()
    adaylar = [u for u in trendyol.urunler() if u["stok"] >= 10 and u["gorseller"]
               and not plan.uygun_mu(u)]
    print(f"{len(adaylar)} hassas ürün var, {ADET} tanesi deneniyor")
    for i, u in enumerate(adaylar[:ADET], start=1):
        for j, url in enumerate(u["gorseller"][:2], start=1):
            try:
                img = gorsel.indir(url)
                soyut, oran = soyutla.soyutla(img)
                img.thumbnail((540, 675))
                img.save(KLASOR / f"{i:02d}-{j}-once.jpg", quality=85)
                if soyut:
                    soyut.thumbnail((540, 675))
                    soyut.save(KLASOR / f"{i:02d}-{j}-sonra.jpg", quality=85)
                print(f"{i:02d}-{j} {u['baslik'][:50]} kıyafet oranı {oran:.2f}")
            except Exception as e:
                print(f"{i:02d}-{j} hata: {e}")


if __name__ == "__main__":
    main()
