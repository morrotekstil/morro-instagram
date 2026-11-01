"""Instagram açıklaması (caption): ürün türüne göre geniş, değişken metin.

Algoritma için: ilk satırda aranan anahtar kelimeler, ürün türüne özel bilgi
paragrafı, ürün özellikleri, kullanım/kombin önerisi, yoruma davet eden bir soru
ve en fazla 5 hashtag (Instagram Aralık 2025'ten beri 5'ten fazlasına izin vermiyor).
Fiyat yazılmaz. Metinler her paylaşımda tohum değerine göre farklı seçilir.
"""
import random

import ayarlar as A

MAKS_ETIKET = 5


def kucuk(m):
    return (m or "").replace("İ", "i").replace("I", "ı").lower()


# Her tür: anahtar kelimeler, bilgi paragrafları, öneriler, sorular, hashtag'ler.
# Sıra önemlidir: ilk eşleşen tür kullanılır.
TURLER = [
    {
        "ad": "tayt",
        "kelimeler": ["tayt"],
        "giris": ["Gün boyu rahat, her harekete uyum sağlayan bir tayt arıyorsan doğru yerdesin.",
                  "Taytın iyisi giyildiğini unutturandır.",
                  "Spor, ev ya da günlük kombin… Bir tayt her yere yetişir."],
        "bilgi": ["Esnek kumaşı sayesinde vücudu sıkmadan sarar; eğilirken, otururken ya da antrenmanda formunu korur. Yüksek ve rahat bel yapısı gün boyu yerinde durur.",
                  "Likralı yapısı hem toparlayıcı bir görünüm verir hem de hareket özgürlüğünü kısıtlamaz. Defalarca yıkamada bile formunu ve rengini korur.",
                  "Hafif dokusu sayesinde hem spor salonunda hem evde hem de elbise altında rahatlıkla kullanılır."],
        "oneri": ["Kombin önerisi: Oversize bir sweatshirt ve beyaz spor ayakkabıyla günlük; uzun bir gömlekle şık bir görünüm.",
                  "Kısa taytları elbise ve etek altına giyerek hem rahat edebilir hem de sürtünmeyi önleyebilirsin.",
                  "Bakım: Ters çevirip 30 derecede yıkarsan esnekliği ve rengi ilk günkü gibi kalır."],
        "soru": ["Tayt giyerken senin için en önemli şey ne: esneklik mi, toparlayıcılık mı? 👇",
                 "Taytını en çok nerede giyiyorsun: sporda mı, evde mi, sokakta mı? Yorumlara yaz 👇",
                 "Senin favori tayt rengin hangisi? Yorumlarda buluşalım 👇"],
        "etiket": ["#tayt", "#kadıntayt", "#sportayt"],
    },
    {
        "ad": "pijama",
        "kelimeler": ["pijama"],
        "giris": ["Evde geçen saatler en rahat haliyle geçmeli.",
                  "Güzel bir uykunun sırrı doğru pijamada.",
                  "Soğuk akşamlarda içini ısıtacak bir pijama takımı arayanlara 🌙"],
        "bilgi": ["Nefes alan pamuklu kumaşı terletmez, cildi tahriş etmez; gece boyu rahat bir uyku sağlar.",
                  "Yumuşak dokusu ve rahat kalıbıyla hem uyurken hem de evde vakit geçirirken üzerinde olduğunu unutursun.",
                  "Yıkadıkça yumuşayan kumaşı ve dayanıklı dikişleriyle uzun süre ilk günkü gibi kalır."],
        "oneri": ["Hediye fikri: Sevdiklerine rahatlık hediye etmek istersen pijama takımı her zaman doğru tercih.",
                  "Bakım: 30 derecede, benzer renklerle yıkayıp asarak kurutursan kumaşı uzun ömürlü olur.",
                  "Bedenini seçerken rahat bir kullanım istiyorsan bir beden büyüğünü de değerlendirebilirsin."],
        "soru": ["Pijama seçerken desen mi, düz renk mi tercih edersin? 👇",
                 "Uzun kollu mu, kısa kollu mu? Kışın hangisiyle uyuyorsun? 👇",
                 "Bu takımı kime hediye ederdin? Etiketle 👇"],
        "etiket": ["#pijama", "#pijamatakımı", "#evgiyim"],
    },
    {
        "ad": "pantolon",
        "kelimeler": ["pantolon", "palazzo", "jogger"],
        "giris": ["Hem şık hem rahat bir pantolon gardıropta her zaman kurtarıcıdır.",
                  "Ofisten akşam yemeğine kadar gün boyu yanında olacak bir parça.",
                  "Rahatlığından ödün vermeden şık görünmek isteyenler için ✨"],
        "bilgi": ["Akışkan kumaşı vücuda yapışmadan düşer, boyu uzun ve ince gösterir. Gün boyu kırışmadan formunu korur.",
                  "Rahat bel yapısı ve kalıbıyla uzun saatler boyunca konforlu kullanım sunar; hem günlük hem şık kombinlere uyum sağlar.",
                  "Mevsim geçişlerinde ve kış aylarında kat kat giyime uygun; ister topukluyla ister spor ayakkabıyla giy."],
        "oneri": ["Kombin önerisi: Düz renk bir triko ve loafer ile ofis şıklığı; crop bir üst ve sneaker ile günlük stil.",
                  "Geniş paça modelleri topuklu ayakkabıyla boyu daha uzun gösterir.",
                  "Bakım: Ütüye fazla ihtiyaç duymaz; düşük ısıda yıkayıp asarak kurutmak yeterli."],
        "soru": ["Pantolonda senin tercihin hangisi: geniş paça mı, dar paça mı? 👇",
                 "Bu pantolonu hangi ayakkabıyla kombinlerdin? 👇",
                 "Ofiste mi, günlükte mi? Sen nerede giyerdin? 👇"],
        "etiket": ["#kadınpantolon", "#pantolon", "#kombin"],
    },
    {
        "ad": "esofman",
        "kelimeler": ["eşofman", "esofman"],
        "giris": ["Rahatlık bir tarzdır.",
                  "Hafta sonunun vazgeçilmezi: rahat bir eşofman takımı.",
                  "Sporda da evde de sokakta da aynı rahatlık."],
        "bilgi": ["Yumuşak dokulu kumaşı içini sıcak tutar, hareket ederken seni kısıtlamaz.",
                  "Lastikli paça ve bel yapısıyla her hareketinde yerinde durur; günlük kullanım için idealdir.",
                  "Yıkadıkça tüylenmeyen kaliteli kumaşıyla uzun süre ilk günkü gibi kalır."],
        "oneri": ["Kombin önerisi: Beyaz spor ayakkabı ve bir şapkayla rahat bir sokak stili.",
                  "Takım olarak ya da altını/üstünü ayrı ayrı farklı parçalarla kombinleyebilirsin.",
                  "Bakım: Ters çevirerek yıkarsan kumaşın yüzeyi daha uzun süre pürüzsüz kalır."],
        "soru": ["Eşofmanı en çok nerede giyiyorsun? 👇",
                 "Takım mı, tek parça mı? Senin tercihin? 👇",
                 "Hafta sonu planın ne? Yorumlara yaz 👇"],
        "etiket": ["#eşofman", "#eşofmantakımı", "#rahatgiyim"],
    },
    {
        "ad": "corap",
        "kelimeler": ["çorap", "corap", "babet"],
        "giris": ["Küçük ama günü değiştiren bir detay: doğru çorap.",
                  "Ayaklarını sıcak ve rahat tutmanın en kolay yolu.",
                  "Çorap çekmecesini yenileme zamanı! 🧦"],
        "bilgi": ["Nefes alan kumaşı ayağı terletmez, gün boyu kuru ve rahat tutar.",
                  "Esnek yapısı ayağı sıkmaz, iz bırakmaz; ayakkabı içinde kaymaz.",
                  "Dayanıklı topuk ve burun yapısıyla uzun süre kullanılır."],
        "oneri": ["İpucu: Babet çoraplar spor ayakkabı ve loafer içinde görünmeden konfor sağlar.",
                  "Bakım: Ters çevirerek yıkarsan tüylenme olmaz.",
                  "Hediye fikri: Çoklu paketler hem pratik hem şık bir küçük hediye."],
        "soru": ["Desenli mi, düz mü? Çorap tercihin hangisi? 👇",
                 "Çorap çekmecende kaç çift tek kalmış çorap var? 😅👇",
                 "Kışın kalın çorap mı, ince çorap mı? 👇"],
        "etiket": ["#çorap", "#çoraptasarım", "#babetçorap"],
    },
    {
        "ad": "termal",
        "kelimeler": ["termal", "içlik", "yün"],
        "giris": ["Kışın üşümeden, kat kat giyinmeden sıcak kalmanın en kolay yolu.",
                  "Soğuklar geldi, içlikler hazır mı? ❄️",
                  "Kalın montlara gerek kalmadan sıcak kalmak mümkün."],
        "bilgi": ["Vücut ısısını içeride tutarken nefes alır; terletmeden sıcak tutar.",
                  "İnce yapısı sayesinde kıyafetin altında hiç belli olmaz, gün boyu rahat hareket edersin.",
                  "Dışarıda çalışanlar, kış sporu yapanlar ve üşümeyi sevmeyenler için ideal bir ilk katman."],
        "oneri": ["İpucu: İçliği tene temas eden ilk katman olarak giy; üzerine bir kat yeterli olur.",
                  "Bakım: Düşük ısıda yıkamak kumaşın ısı tutma özelliğini korur.",
                  "Takım olarak altı ve üstüyle birlikte kullanırsan en iyi sonucu alırsın."],
        "soru": ["Kışın sen de çok üşüyenlerden misin? 👇",
                 "İçlik giymeden kışı geçirebilenler var mı? 👇",
                 "En soğuk günde kaç kat giyiniyorsun? 👇"],
        "etiket": ["#termaliçlik", "#içlik", "#kışgiyim"],
    },
    {
        "ad": "boxer",
        "kelimeler": ["boxer"],
        "giris": ["Gün boyu rahatlığın temeli doğru iç çamaşırından geçer.",
                  "Konforu hissettiren, varlığını unutturan boxer.",
                  "Erkek iç giyimde rahatlık ve kalite bir arada."],
        "bilgi": ["Esnek ve nefes alan kumaşı terletmez, sıkmaz; gün boyu yerinde durur.",
                  "Yumuşak bel lastiği iz bırakmaz, dikişleri tahriş etmez.",
                  "Çoklu paket seçeneğiyle hem ekonomik hem her gün için hazır."],
        "oneri": ["İpucu: Bedeninizi seçerken bel ölçünüzü baz alın; rahat kalıbı gün boyu konfor sağlar.",
                  "Bakım: 40 derecede, benzer renklerle yıkayın; kumaş formunu korur.",
                  "Hediye fikri: Babaya, eşe, abiye pratik ve işe yarar bir hediye."],
        "soru": ["Boxer seçerken senin için en önemli şey ne: kumaş mı, kalıp mı? 👇",
                 "Düz renk mi, desenli mi? 👇",
                 "Kime hediye ederdin? Etiketle 👇"],
        "etiket": ["#boxer", "#erkekboxer", "#erkekiçgiyim"],
    },
    {
        "ad": "atlet",
        "kelimeler": ["atlet", "fanila", "body", "badi"],
        "giris": ["Her mevsimin vazgeçilmez temel parçası.",
                  "Gömleğin altında da tek başına da rahat.",
                  "Basic ama olmazsa olmaz 🤍"],
        "bilgi": ["Pamuklu, nefes alan kumaşı teri emer, cildi rahatlatır; gün boyu ferah hissettirir.",
                  "Vücudu saran kalıbıyla kıyafetin altında belli olmaz, gömlek ve tişört altında iz yapmaz.",
                  "Çok yıkamaya dayanıklı yapısıyla uzun süre beyazlığını ve formunu korur."],
        "oneri": ["İpucu: Gömlek altında ter izini önlemek için ince bir atlet en pratik çözüm.",
                  "Bakım: Beyazları ayrı yıkamak rengin uzun süre canlı kalmasını sağlar.",
                  "Çoklu paketler sayesinde haftanın her günü için hazırsın."],
        "soru": ["Atleti tek başına mı, gömlek altında mı giyiyorsun? 👇",
                 "Atleti hangi mevsimde daha çok giyiyorsun? 👇",
                 "Sen de basic parçaları stoklayanlardan mısın? 👇"],
        "etiket": ["#atlet", "#fanila", "#basic"],
    },
    {
        "ad": "sort",
        "kelimeler": ["şort", "sort"],
        "giris": ["Evde rahatlık, dışarıda şıklık.",
                  "Rahat bir şort takımla günün tadını çıkar.",
                  "Her mevsim ev içinde vazgeçilmez."],
        "bilgi": ["Yumuşak ve nefes alan kumaşıyla gün boyu ferah hissettirir.",
                  "Rahat kalıbı hareket özgürlüğü sağlar; hem uyurken hem evde ideal.",
                  "Kaliteli dikişleri ve dayanıklı kumaşıyla uzun süre formunu korur."],
        "oneri": ["İpucu: Ev içinde rahatlık için şort takımlar en pratik seçim.",
                  "Bakım: 30 derecede yıkayıp asarak kurutun.",
                  "Hediye fikri: Sevdiklerine rahat bir ev takımı hediye et."],
        "soru": ["Evde en çok ne giymeyi seviyorsun? 👇",
                 "Şort mu, uzun alt mı? 👇",
                 "Bu takımın hangi rengi senin tarzın? 👇"],
        "etiket": ["#şorttakım", "#evgiyim", "#rahatgiyim"],
    },
    {
        "ad": "tisort",
        "kelimeler": ["tişört", "tisort", "t-shirt", "sweatshirt", "sweat"],
        "giris": ["Gardırobun en çok giyilen parçası: iyi bir basic.",
                  "Sade, rahat ve her şeyle uyumlu.",
                  "Kombinin temelini sağlam at."],
        "bilgi": ["Pamuklu kumaşı nefes alır, yıkadıkça yumuşar; gün boyu rahat kullanılır.",
                  "Düzgün kalıbı sayesinde hem tek başına hem ceket altında şık durur.",
                  "Yıkamada formunu ve rengini koruyan kaliteli bir parça."],
        "oneri": ["Kombin önerisi: Jean ve beyaz ayakkabıyla klasik; eşofman altıyla rahat bir görünüm.",
                  "Bakım: Ters çevirip düşük ısıda yıkarsan rengi uzun süre canlı kalır.",
                  "Farklı renkleriyle haftanın her gününe bir kombin."],
        "soru": ["Basic parçalarda en sevdiğin renk hangisi? 👇",
                 "Bu parçayı neyle kombinlerdin? 👇",
                 "Regular fit mi, oversize mı? 👇"],
        "etiket": ["#tişört", "#basic", "#kombin"],
    },
    {
        "ad": "kulot",
        "kelimeler": ["külot", "kulot", "slip"],
        "giris": ["Rahatlık en içten başlar.",
                  "Her gün için konforlu bir seçim.",
                  "İç giyimde kalite fark yaratır."],
        "bilgi": ["Pamuklu, nefes alan kumaşı cildi rahatlatır, gün boyu ferah hissettirir.",
                  "Yumuşak lastikleri iz bırakmaz, kıyafet altında belli olmaz.",
                  "Çoklu paket seçenekleriyle hem ekonomik hem pratik."],
        "oneri": ["Bakım: 40 derecede, benzer renklerle yıkayın.",
                  "İpucu: Pamuklu iç giyim cilt sağlığı için en iyi tercihtir.",
                  "Çoklu paketlerle haftanın her günü için hazırsın."],
        "soru": ["İç giyimde senin önceliğin ne: kumaş mı, kalıp mı? 👇",
                 "Çoklu paket mi, tekli mi tercih edersin? 👇",
                 "En çok hangi rengi kullanıyorsun? 👇"],
        "etiket": ["#külot", "#pamukluiçgiyim", "#içgiyim"],
    },
]

GENEL = {
    "ad": "genel",
    "giris": ["Rahatlık ve kalite bir arada.", "Günlük hayatın vazgeçilmez parçası.",
              "Her gün giymek isteyeceğin bir parça."],
    "bilgi": ["Kaliteli kumaşı ve özenli dikişleriyle uzun süre ilk günkü gibi kalır.",
              "Rahat kalıbı ve yumuşak dokusuyla gün boyu konfor sağlar."],
    "oneri": ["Bakım: Düşük ısıda, benzer renklerle yıkamak ürünün ömrünü uzatır.",
              "Hediye fikri: Sevdiklerine pratik ve işe yarar bir hediye."],
    "soru": ["Bu ürünü kime hediye ederdin? Etiketle 👇", "Hangi rengi tercih ederdin? 👇"],
    "etiket": ["#içgiyim", "#evgiyim", "#rahatgiyim"],
}

CINSIYET_ETIKET = {"kadın": "#kadıngiyim", "erkek": "#erkekgiyim", "çocuk": "#çocukgiyim"}


def tur_bul(baslik, kategori=""):
    metin = kucuk(baslik) + " " + kucuk(kategori)
    for t in TURLER:
        if any(k in metin for k in t["kelimeler"]):
            return t
    return GENEL


def etiketler(tur, baslik, morro):
    sec = list(tur["etiket"][:3])
    b = kucuk(baslik)
    if len(sec) < 4:
        for k, v in CINSIYET_ETIKET.items():
            if k in b and v not in sec:
                sec.append(v)
                break
    sec.append("#morro" if morro else "#morroicgiyim")
    if len(sec) < MAKS_ETIKET:
        sec.append("#morroicgiyim" if morro else "#trendyol")
    return " ".join(dict.fromkeys(sec[:MAKS_ETIKET]))


def olustur(u, detaylar, tohum, morro=False, kampanya=None):
    """u: ürün (baslik, kategori). detaylar: [(ikon, ad, değer)]. Açıklama metni döndürür."""
    rnd = random.Random(str(tohum))
    tur = tur_bul(u["baslik"], u.get("kategori", ""))
    s = [u["baslik"], "", rnd.choice(tur["giris"]), "", rnd.choice(tur["bilgi"]), "", "✨ Ürün özellikleri"]
    for ik, ad, deger in detaylar:
        if str(deger).strip().lower() == "belirtilmemiş":
            continue
        s.append(f"{ik} {ad}: {deger}")
    s += ["", "💡 " + rnd.choice(tur["oneri"])]
    if kampanya:
        s += ["", kampanya["aciklama"]]
    s += ["", "🛒 Trendyol'da Morro mağazamızda ve morro.com.tr'de. Link profilde!",
          "", rnd.choice(tur["soru"]), "", etiketler(tur, u["baslik"], morro)]
    return "\n".join(s)
