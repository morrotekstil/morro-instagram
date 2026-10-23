"""Kalıcı durum: paylaşım geçmişi, günlük plan, şifreli token."""
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken

KOK = Path(__file__).parent
TR = ZoneInfo("Europe/Istanbul")
GECMIS = KOK / "state" / "paylasimlar.json"
TOKEN_DOSYA = KOK / "state" / "token.enc"
TOKEN_META = KOK / "state" / "token.json"


def simdi():
    return dt.datetime.now(TR)


def bugun():
    return simdi().date().isoformat()


def oku(yol, varsayilan):
    yol = Path(yol)
    if yol.exists():
        return json.loads(yol.read_text(encoding="utf-8"))
    return varsayilan


def yaz(yol, veri):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")


def plan_yolu(tarih=None):
    return KOK / "plan" / f"{tarih or bugun()}.json"


# --- Token ---------------------------------------------------------------
# Yenilenen token depoda şifreli saklanır. Anahtar, GitHub Secrets'taki
# IG_TOKEN değerinden türetilir; o değer kimsede olmadan dosya çözülemez.

def _fernet():
    kaynak = os.environ.get("IG_TOKEN", "").strip()
    if not kaynak:
        raise RuntimeError("IG_TOKEN gizli anahtarı tanımlı değil")
    anahtar = base64.urlsafe_b64encode(hashlib.sha256(("morro:" + kaynak).encode()).digest())
    return Fernet(anahtar)


def token_al():
    if TOKEN_DOSYA.exists():
        try:
            return _fernet().decrypt(TOKEN_DOSYA.read_bytes()).decode()
        except InvalidToken:
            pass  # IG_TOKEN değiştirilmiş: yeni token'ı kullan
    return os.environ["IG_TOKEN"].strip()


def token_kaydet(token, sure_sn):
    TOKEN_DOSYA.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_DOSYA.write_bytes(_fernet().encrypt(token.encode()))
    yaz(TOKEN_META, {
        "son_yenileme": simdi().isoformat(timespec="minutes"),
        "bitis": (simdi() + dt.timedelta(seconds=sure_sn)).date().isoformat() if sure_sn else None,
    })


def token_yenilenmeli(gun=5):
    meta = oku(TOKEN_META, {})
    son = meta.get("son_yenileme")
    if not son:
        return True
    return simdi() - dt.datetime.fromisoformat(son) > dt.timedelta(days=gun)
