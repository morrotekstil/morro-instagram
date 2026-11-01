"""Reels için sakin, telifsiz fon müziği üretir.

Her video için tohum (seed) değerine göre farklı bir tarz, ton, tempo ve akor
yürüyüşü seçilir; böylece müzik her paylaşımda değişir ama hep yumuşak kalır.
Tarzlar: piyano, ambiyans, akustik gitar, lo-fi, müzik kutusu, yumuşak bossa.
"""
import random
import wave

import numpy as np

SR = 44100

# Sakin akor yürüyüşleri (do majöre göre yarım ses; 0 = do)
YURUYUSLER = [
    [(0, "maj7"), (9, "m7"), (5, "maj7"), (7, "6")],      # I - vi - IV - V
    [(2, "m7"), (7, "7sus"), (0, "maj7"), (9, "m7")],     # ii - V - I - vi
    [(0, "maj7"), (4, "m7"), (5, "maj7"), (5, "m6")],     # I - iii - IV - iv
    [(9, "m7"), (5, "maj7"), (0, "maj7"), (7, "6")],      # vi - IV - I - V
    [(0, "maj9"), (5, "maj9"), (0, "maj9"), (5, "maj9")], # I - IV salınımı
    [(5, "maj7"), (4, "m7"), (2, "m7"), (0, "maj7")],     # IV - iii - ii - I
]
AKOR = {
    "maj7": [0, 4, 7, 11], "maj9": [0, 4, 7, 11, 14], "m7": [0, 3, 7, 10],
    "6": [0, 4, 7, 9], "m6": [0, 3, 7, 9], "7sus": [0, 5, 7, 10],
}
TARZLAR = ["piyano", "ambiyans", "gitar", "lofi", "muzik_kutusu", "bossa"]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _ekle(ses, bas, sinyal, kazanc=1.0):
    b = int(bas * SR)
    if b >= len(ses) or b < 0:
        return
    e = min(len(ses), b + len(sinyal))
    ses[b:e] += sinyal[: e - b] * kazanc


def _piyano(f, sure=2.5, parlak=0.4):
    t = np.arange(int(sure * SR)) / SR
    zarf = np.exp(-t * 2.2) * np.minimum(t / 0.006, 1)
    s = np.sin(2 * np.pi * f * t) + parlak * np.sin(4 * np.pi * f * t) * np.exp(-t * 4) \
        + 0.15 * np.sin(6 * np.pi * f * t) * np.exp(-t * 7)
    return s * zarf


def _ped(f, sure, atak=0.8):
    t = np.arange(int(sure * SR)) / SR
    zarf = np.minimum(t / atak, 1) * np.minimum((sure - t) / max(atak, 0.3), 1)
    s = sum(np.sin(2 * np.pi * f * d * t + d) for d in (0.997, 1.0, 1.004)) / 3
    s += 0.25 * np.sin(4 * np.pi * f * t)
    vib = 1 + 0.15 * np.sin(2 * np.pi * 0.3 * t)
    return s * zarf * vib


def _gitar(f, sure=1.6, parlaklik=0.996):
    """Karplus-Strong telli çalgı sesi."""
    n = int(SR / f)
    if n < 2:
        return np.zeros(int(sure * SR))
    rng = np.random.default_rng(int(f * 100))
    tampon = rng.uniform(-1, 1, n)
    tampon = np.convolve(tampon, np.ones(3) / 3, mode="same")  # daha yumuşak tını
    bloklar, toplam = [], int(sure * SR)
    while sum(len(b) for b in bloklar) < toplam:
        bloklar.append(tampon)
        tampon = parlaklik * 0.5 * (tampon + np.roll(tampon, 1))
    s = np.concatenate(bloklar)[:toplam]
    return s * np.minimum(np.arange(toplam) / (0.004 * SR), 1)


def _can(f, sure=1.8):
    """Müzik kutusu / çelesta."""
    t = np.arange(int(sure * SR)) / SR
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 6)) \
        * np.exp(-t * 3.2) * np.minimum(t / 0.003, 1)


def _yumusak_vurus(sure=0.3):
    t = np.arange(int(sure * SR)) / SR
    return np.sin(2 * np.pi * (45 * t + 30 * (1 - np.exp(-t * 30)))) * np.exp(-t * 16)


def _firca(rng, sure=0.12):
    n = int(sure * SR)
    gurultu = rng.standard_normal(n)
    gurultu = np.convolve(gurultu, np.ones(6) / 6, mode="same")
    return gurultu * np.exp(-np.arange(n) / SR * 35)


def uret(sure, yol, tohum=None):
    """sure saniyelik stereo WAV üretir; seçilen tarzı döndürür."""
    rnd = random.Random(tohum)
    tarz = rnd.choice(TARZLAR)
    ton = rnd.choice([-5, -3, -2, 0, 2, 3, 5])
    yuruyus = rnd.choice(YURUYUSLER)
    tempo = {"piyano": (66, 80), "ambiyans": (60, 70), "gitar": (76, 90), "lofi": (70, 82),
             "muzik_kutusu": (72, 88), "bossa": (84, 96)}[tarz]
    bpm = rnd.uniform(*tempo)
    vurus = 60 / bpm
    olcu = vurus * 4
    n = int(sure * SR)
    ses = np.zeros(n)
    rng = np.random.default_rng(rnd.randint(0, 10**6))
    kok = 48 + ton  # do3 civarı

    i = 0
    while i * olcu < sure:
        derece, tip = yuruyus[i % len(yuruyus)]
        notalar = [kok + derece + a for a in AKOR[tip]]
        bas_t = i * olcu
        bas_nota = kok - 12 + derece
        if tarz == "piyano":
            for j, m in enumerate(notalar):  # hafif arpejli akor
                _ekle(ses, bas_t + j * 0.04, _piyano(hz(m + 12), 3.0, 0.3), 0.11)
            _ekle(ses, bas_t, _piyano(hz(bas_nota), 3.2, 0.2), 0.16)
            for k in range(rnd.choice([1, 2, 2, 3])):  # seyrek melodi
                m = rnd.choice(notalar) + 24
                _ekle(ses, bas_t + rnd.choice([1, 2, 2.5, 3]) * vurus, _piyano(hz(m), 2.0, 0.5), 0.07)
        elif tarz == "ambiyans":
            for m in notalar:
                _ekle(ses, bas_t, _ped(hz(m + 12), olcu + 1.2, 1.2), 0.07)
            _ekle(ses, bas_t, _ped(hz(bas_nota), olcu + 1.2, 1.0), 0.10)
            if rnd.random() < 0.7:
                _ekle(ses, bas_t + rnd.choice([1, 2]) * vurus, _can(hz(rnd.choice(notalar) + 24), 2.5), 0.05)
        elif tarz == "gitar":
            desen = [0, 2, 1, 3, 2, 1, 3, 2]
            for j, d in enumerate(desen):
                m = notalar[d % len(notalar)] + 12
                _ekle(ses, bas_t + j * vurus / 2, _gitar(hz(m), 1.6), 0.13)
            _ekle(ses, bas_t, _gitar(hz(bas_nota), 2.5, 0.997), 0.18)
        elif tarz == "lofi":
            for m in notalar:
                _ekle(ses, bas_t + 0.02, _piyano(hz(m + 12), olcu, 0.15) * 0.9, 0.09)
            _ekle(ses, bas_t, _ped(hz(bas_nota), olcu, 0.1), 0.12)
            for b in range(4):  # çok hafif ritim
                if b in (0, 2):
                    _ekle(ses, bas_t + b * vurus, _yumusak_vurus(), 0.16)
                else:
                    _ekle(ses, bas_t + b * vurus, _firca(rng), 0.035)
            if rnd.random() < 0.8:
                _ekle(ses, bas_t + 2.5 * vurus, _piyano(hz(rnd.choice(notalar) + 24), 1.5, 0.4), 0.06)
        elif tarz == "muzik_kutusu":
            sira = [0, 1, 2, 3, 2, 1, 2, 3] if rnd.random() < 0.5 else [3, 2, 1, 0, 1, 2, 3, 2]
            for j, d in enumerate(sira):
                _ekle(ses, bas_t + j * vurus / 2, _can(hz(notalar[d % len(notalar)] + 24)), 0.08)
            for m in notalar[:3]:
                _ekle(ses, bas_t, _ped(hz(m), olcu + 0.8, 0.9), 0.05)
        else:  # bossa: yumuşak gitar ritmi + bas
            for j, b in enumerate([0, 1.5, 3, 4.5, 6]):
                for m in notalar[1:]:
                    _ekle(ses, bas_t + b * vurus / 2 + 0.01 * j, _gitar(hz(m + 12), 0.8, 0.993), 0.06)
            _ekle(ses, bas_t, _gitar(hz(bas_nota), 1.2, 0.997), 0.17)
            _ekle(ses, bas_t + 2 * vurus, _gitar(hz(bas_nota + 7), 1.2, 0.997), 0.14)
            for b in range(8):
                _ekle(ses, bas_t + b * vurus / 2, _firca(rng, 0.08), 0.02)
        i += 1

    # oda yankısı (basit gecikmeler), giriş/çıkış, ses seviyesi
    for gecikme, kazanc in ((0.11, 0.25), (0.23, 0.15), (0.37, 0.08)):
        g = int(gecikme * SR)
        ses[g:] += ses[:-g] * kazanc
    t = np.arange(n) / SR
    ses *= np.minimum(t / 1.0, 1) * np.minimum((sure - t) / 2.0, 1)
    rms = float(np.sqrt(np.mean(ses ** 2))) or 1
    ses = np.tanh(ses / rms * 0.11 / 0.85) * 0.85  # tüm tarzlar benzer ses seviyesinde
    sol = ses
    sag = np.roll(ses, int(0.012 * SR))
    veri = (np.stack([sol, sag], axis=1) * 32767).astype(np.int16)
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(veri.tobytes())
    return tarz
