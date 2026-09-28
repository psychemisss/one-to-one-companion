import json
from pathlib import Path

from loguru import logger

from app.config import settings

LANGS = ("en", "ru")
_STRINGS = {lang: json.loads((Path(__file__).parent / "i18n" / f"{lang}.json").read_text("utf-8")) for lang in LANGS}


def t(key, lang, **kwargs):
    s = _STRINGS.get(lang, {}).get(key) or _STRINGS["en"].get(key) or key
    return s.format(**kwargs) if kwargs else s


def resolve_lang(cookie):
    return cookie if cookie in LANGS else settings.app.default_language


def check_sync():
    keys = {lang: set(s) for lang, s in _STRINGS.items()}
    for lang in LANGS:
        missing = sorted(set().union(*keys.values()) - keys[lang])
        if missing:
            logger.warning("i18n: {} is missing keys: {}", lang, ", ".join(missing))
