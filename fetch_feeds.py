#!/usr/bin/env python3
"""Scarica i feed elencati in feeds.json e scrive news.json."""
import json, re, html, time, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

UA = ("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Mobile Safari/537.36")
MAX_ITEMS = 40


def local(tag):
    return tag.rsplit("}", 1)[-1]


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return 0
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return 0
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


IMG_EXT = re.compile(r"\.(jpe?g|png|webp|gif|avif)(\?|#|$)", re.I)
IMG_TAG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)


def norm_img(u):
    u = (u or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    if u.startswith("http://"):
        u = "https://" + u[7:]
    return u if u.startswith("https://") else ""


def find_image(n, f):
    """Cerca l'immagine: enclosure / media:content / media:thumbnail, poi <img> nel testo."""
    for c in n.iter():
        k = local(c.tag)
        u = c.get("url") or ""
        if not u or k not in ("enclosure", "content", "thumbnail"):
            continue
        t = (c.get("type") or "") + (c.get("medium") or "")
        if k == "thumbnail" or "image" in t or (not t and IMG_EXT.search(u)):
            u = norm_img(u)
            if u:
                return u
    for key in ("description", "encoded", "summary", "content"):
        m = IMG_TAG.search(f.get(key) or "")
        if m:
            u = norm_img(html.unescape(m.group(1)))
            if u:
                return u
    return ""


def parse(data):
    root = ET.fromstring(data)
    items = []
    for n in root.iter():
        if local(n.tag) not in ("item", "entry"):
            continue
        f = {}
        for c in n:
            k = local(c.tag)
            if k == "link":
                if not f.get("link"):
                    f["link"] = c.get("href") or (c.text or "").strip()
            elif k not in f:
                f[k] = (c.text or "").strip()
        title = clean(f.get("title"))
        link = f.get("link", "")
        if not title or not link:
            continue
        date = f.get("pubDate") or f.get("published") or f.get("updated") or f.get("date")
        desc = clean(f.get("description") or f.get("summary") or f.get("content"))[:220]
        item = {"title": title, "desc": desc, "link": link, "ts": parse_date(date)}
        img = find_image(n, f)
        if img:
            item["img"] = img
        items.append(item)
        if len(items) >= MAX_ITEMS:
            break
    if not items:
        raise ValueError("nessun articolo trovato nel feed")
    return items


def fetch(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
                "Accept-Language": "it-IT,it;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2)
    raise last


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def main():
    feeds = load_json("feeds.json", [])
    old = load_json("news.json", {"feeds": []})
    old_items = {f["url"]: f.get("items", []) for f in old.get("feeds", [])}
    out = []
    for f in feeds:
        entry = {"name": f["name"], "url": f["url"], "error": None, "items": []}
        try:
            entry["items"] = parse(fetch(f["url"]))
        except Exception as e:
            entry["error"] = (type(e).__name__ + ": " + str(e))[:140]
            entry["items"] = old_items.get(f["url"], [])
        out.append(entry)
        print(("OK   " if not entry["error"] else "ERR  ") + f["name"], entry["error"] or len(entry["items"]))
    if out == old.get("feeds"):
        print("Nessuna novità, file invariato.")
        return
    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "feeds": out}
    with open("news.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print("news.json aggiornato.")


if __name__ == "__main__":
    main()
