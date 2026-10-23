"""Morro Instagram otomasyonu - ayarlar.

Bu dosyadaki değerleri değiştirerek programın davranışını ayarlayabilirsin.
Gizli bilgiler (token, API anahtarları) burada DEĞİL, GitHub Secrets'ta durur.
"""
import os

# Instagram hesabı (@morroicgiyim) - gizli değil
IG_USER_ID = os.environ.get("IG_USER_ID", "17841407152280652")
IG_API = "https://graph.instagram.com/v23.0"

# Paylaşım saatleri (Türkiye saati)
SAATLER = ["12:30", "18:30", "21:00"]

# Ürün seçimi
MIN_STOK = 10            # toplam stoğu bundan az olan ürün paylaşılmaz
TEKRAR_GUN = 21          # bir ürün en erken kaç gün sonra tekrar paylaşılır
YEDEK_SAYISI = 3         # stok biterse yerine geçecek yedek ürün sayısı
FIYAT_TAKIP_GUN = 30     # fiyat değişikliği kaç günlük paylaşımlar için izlenir
MIN_INDIRIM = 5          # bu yüzdenin altındaki indirimler etikete yazılmaz

# Deponun herkese açık ham dosya adresi (görseller Instagram'a buradan verilir)
REPO = os.environ.get("GITHUB_REPOSITORY", "morrotekstil/morro-instagram")
DAL = os.environ.get("GITHUB_REF_NAME", "main")
HAM_ADRES = f"https://raw.githubusercontent.com/{REPO}/{DAL}"


# Sadece deneme: 1 ise Instagram'a hiçbir şey gönderilmez
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

# Görsel
GENISLIK, YUKSEKLIK = 1080, 1350   # Instagram 4:5 dikey
ETIKET_RENK = (198, 40, 40)         # kırmızı
MARKA_ETIKET = "MORRO İÇ GİYİM"     # indirim yoksa yazılacak etiket

# Başlığa göre eklenen hashtag'ler
ETIKETLER = {
    "boxer": "#boxer #erkekboxer #erkekiçgiyim",
    "külot": "#külot #kadıniçgiyim #pamuklukülot",
    "kulot": "#külot #kadıniçgiyim",
    "slip": "#slip #külot",
    "çorap": "#çorap #çoraptasarım #günlükçorap",
    "babet": "#babetçorap #görünmezçorap",
    "tayt": "#tayt #sportayt #toparlayıcıtayt",
    "pijama": "#pijama #pijamatakımı #evgiyim",
    "sütyen": "#sütyen #kadıniçgiyim",
    "atlet": "#atlet #erkekatlet",
    "bambu": "#bambu #bambuboxer",
    "hamile": "#hamile #hamilegiyim",
    "çocuk": "#çocukiçgiyim",
}
SABIT_ETIKETLER = "#morro #morroicgiyim #içgiyim #trendyol"
