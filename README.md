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

## Buybox takibi (deneme: 3 ürün)

`buybox.py` her yarım saatte (08:07–23:37) Trendyol API'sinden buybox bilgisini okur ve
`buybox/urunler.csv` dosyasındaki ürünlerin fiyatını rakibin %1 altına ayarlar:
fiyat hiçbir zaman **taban**ın (kâr kuralı) altına inmez, **tavan**ın (DLAP fiyatı) üstüne çıkmaz.
Rakip fiyat yükseltirse bizim fiyatımız da yükselir. Yapılan her değişiklik `buybox/kayit/` altına yazılır.

- Bir ürünü geçici olarak takipten çıkarmak (flaş teklif, kampanya): `aktif` sütununu `0` yap.
- Kurallar: `normal` (%10 kâr), `kis300` (en az 300 TL kâr, U.S. Polo kışlık), `basabas` (zarar yok).
- Elle çalıştırma: Actions → "Buybox takibi" → Run workflow (deneme işaretliyse fiyat değiştirmez).
