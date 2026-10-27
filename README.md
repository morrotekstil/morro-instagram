# Morro Instagram otomasyonu

@morroicgiyim hesabına her gün 3 gönderi atar: 12:30, 18:30 ve 21:00 (Türkiye saati).

## Nasıl çalışır

1. **Her sabah 07:00:** "Günlük plan" çalışır.
   - Trendyol'dan stoktaki ürünleri çeker ve son 21 günde paylaşılmamış 3 ürün seçer (3 de yedek).
   - Her ürünün görselini 1080x1350 boyutuna getirir, üstüne etiket koyar ("%30 İNDİRİM" ya da indirim yoksa "MORRO İÇ GİYİM").
   - Fiyatlı açıklamayı ve hashtag'leri hazırlar.
   - Son 30 günde paylaşılan ürünlerin fiyatı değiştiyse listeler.
   - Sonuç `plan/bugun.json` dosyasına yazılır, sabah raporu önizlemeyi buradan alır.
2. **12:30, 18:30, 21:00:** "Instagram paylaşımı" sıradaki ürünü paylaşır. Ürünün stoğu bittiyse yerine yedek geçer.
3. Instagram token'ı birkaç günde bir otomatik uzatılır (şifreli olarak `state/` içinde saklanır).

## Bir paylaşımı iptal etmek

`plan/GGGG-AA-GG.json` dosyasında ilgili kalemin `"durum": "bekliyor"` değerini `"iptal"` yap.

## Gizli anahtarlar (Settings → Secrets and variables → Actions)

| Ad | Ne |
|---|---|
| `IG_TOKEN` | Meta panelindeki "Token oluştur" ile alınan Instagram token'ı |
| `TRENDYOL_SELLER_ID` | Trendyol satıcı ID |
| `TRENDYOL_API_KEY` | Trendyol API Key |
| `TRENDYOL_API_SECRET` | Trendyol API Secret |

## Ayarlar

Paylaşım saatleri, minimum stok, tekrar aralığı ve hashtag'ler `ayarlar.py` dosyasındadır.

## Buybox takibi (Trendyol, tüm ürünler)

`buybox.py` her yarım saatte (08:07–23:37) Trendyol API'sinden satıştaki tüm ürünleri ve buybox
bilgisini okur, fiyatı rakibin %1 altına ayarlar. Fiyat hiçbir zaman **taban**ın (kâr kuralı) altına
inmez, **tavan**ın (DLAP fiyatı) üstüne çıkmaz. Rakip fiyat yükseltirse bizim fiyatımız da yükselir.

| Kural | Hangi ürünler | Taban |
|---|---|---|
| 300 TL kâr | U.S. Polo kışlık (pijama, ev giyim, gecelik; kısa kollu ve boxer hariç) | en az 300 TL net kâr |
| Başabaş | Pierre Cardin sütyen/sütyen takımları; U.S. Polo, Pierre Cardin, Pijapia kısa kollu/yazlık | zarar yok |
| %10 kâr | diğer tüm ürünler | maliyet +%10 |

- **Morro** ürünlerine dokunulmaz. Fiyatı zaten tabanın altında olan %10/başabaş ürünlere de dokunulmaz (eritiliyor sayılır).
- Maliyet ve DLAP fiyatları `buybox/maliyetler.csv` dosyasındadır (stok kodu;maliyet;tavan). Maliyet değişince bu dosya güncellenmeli.
- Bir ürünü geçici olarak takipten çıkarmak (flaş teklif, kampanya) veya kuralını değiştirmek: `buybox/istisnalar.csv` dosyasına `barkod,kural,aktif,not` satırı ekle (aktif `0` → dokunma).
- Son durum `buybox/son_durum.md`, yapılan her değişiklik `buybox/kayit/` altında.
- Elle çalıştırma: Actions → "Buybox takibi" → Run workflow (deneme işaretliyse fiyat değiştirmez).
