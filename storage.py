import json
import os
import uuid
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
FILE = DATA_DIR / "addresses.json"

DEFAULTS = [
    {"id": "kabul", "name": "کابل",
     "address": "کابل - سرای شهزاده منزل دوم دکان A161 صرافی شبیراحمد", "default": True},
    {"id": "kandahar", "name": "کندهار",
     "address": "کندهار - تجارتی مارکت منزل اول دکان 29 صرافی رفیع عزیزی", "default": False},
]


def norm(s: str) -> str:
    return s.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ").strip().lower()


def load():
    if FILE.exists():
        try:
            data = json.loads(FILE.read_text(encoding="utf-8"))
            if data:
                return data
        except Exception:
            pass
    return [dict(d) for d in DEFAULTS]


def save(items):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if items and not any(i.get("default") for i in items):
        items[0]["default"] = True
    FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert(name, address):
    items = load()
    for i in items:
        if norm(i["name"]) == norm(name):
            i["name"], i["address"] = name, address
            save(items)
            return
    items.append({"id": uuid.uuid4().hex[:6], "name": name, "address": address, "default": False})
    save(items)


def delete(addr_id) -> bool:
    items = load()
    if len(items) <= 1:
        return False
    items = [i for i in items if i["id"] != addr_id]
    save(items)
    return True


def set_default(addr_id):
    items = load()
    for i in items:
        i["default"] = i["id"] == addr_id
    save(items)


def find_for_line(line: str):
    """اگر نام یکی از آدرس‌ها در خط چهارم بود همان، وگرنه آدرس پیش‌فرض."""
    items = load()
    n = norm(line or "")
    if n:
        for i in items:
            if norm(i["name"]) in n:
                return i
    return next((i for i in items if i.get("default")), items[0])
