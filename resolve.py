#!/usr/bin/env python3
"""BeyazElma ailesinden canli mac + spor kanallarini cozup liste.m3u ve kanallar/*.m3u8 uretir.
Stdlib-only. Cikti dogrulamali: sadece #EXTM3U donduren yayinlar yazilir.
"""
import base64
import concurrent.futures as cf
import json
import os
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
DOMAINS_URL = "https://raw.githubusercontent.com/Wiojelt/TurkSpor/main/domains.json"
FAMILY = ["beyazelma", "selcuksports", "taraftarium24", "mackeyfi", "zbahistv",
          "papazsports", "ardaspor", "mahsunsports", "inattv", "betmatiktv",
          "intersportv", "livextv", "crex"]
FALLBACK = {"beyazelma": "https://beyazelma78.com/"}
LOGO_BASE = "https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/turkey/"
TR_LOGOS = {"bein sports haber": "bein-sports-haber-tr.png", "s sport plus": "s-sport-plus-tr.png",
            "s sport 2": "s-sport-2-tr.png", "s sport": "s-sport-tr.png",
            "trt spor y": "trt-spor-yildiz-tr.png", "trt spor": "trt-spor-tr.png",
            "a spor": "a-spor-tr.png", "sports tv": "sports-tv-tr.png",
            "spor smart": "spor-smart-hd-tr.png", "trt 1": "trt-1-tr.png"}
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def http(url, referer=None, origin=None, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*",
                                               "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"})
    if referer:
        req.add_header("Referer", referer)
    if origin:
        req.add_header("Origin", origin)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def first_working(urls):
    for u in urls:
        if not u or not u.startswith("http"):
            continue
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA}, method="HEAD")
            with urllib.request.urlopen(req, timeout=8) as r:
                if 200 <= r.status < 400:
                    return u
        except Exception:
            try:  # HEAD kapaliysa kisa GET
                req = urllib.request.Request(u, headers={"User-Agent": UA, "Range": "bytes=0-0"})
                with urllib.request.urlopen(req, timeout=8):
                    return u
            except Exception:
                pass
    return None


def resolve_origins():
    try:
        sources = json.loads(http(DOMAINS_URL, timeout=15))["sources"]
    except Exception as e:
        print("domains.json erisilemedi:", e)
        sources = {}
    out = {}

    def pick(key):
        src = sources.get(key, {})
        cands = list(src.get("candidates", [])) + list(src.get("gateways", []))
        if key in FALLBACK:
            cands.append(FALLBACK[key])
        return key, first_working(cands)

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for key, url in ex.map(pick, FAMILY):
            if url:
                out[key] = url.rstrip("/")
                print("site:", key, "->", url)
    return out


def slug_title(slug, keep_numbers=False):
    s = slug if keep_numbers else re.sub(r"-\d{10,}$", "", slug)
    words = []
    for w in s.split("-"):
        if not w:
            continue
        lw = w.lower()
        if lw == "vs":
            words.append("vs")
        elif lw in ("fhd", "hd", "4k"):
            words.append(lw.upper())
        elif w.isdigit():
            words.append(w)
        elif lw in ("tv", "ufc", "atv", "dazn", "tv8"):
            words.append(lw.upper())
        else:
            words.append(w[0].upper() + w[1:])
    return " ".join(words)


def tr_logo(name):
    n = name.lower()
    for k, v in TR_LOGOS.items():
        if k in n:
            return LOGO_BASE + v
    return ""


def favicon(origin):
    return "https://www.google.com/s2/favicons?domain=" + urllib.parse.urlparse(origin).hostname + "&sz=128"


def list_links(origin, page, prefix):
    try:
        html = http(origin + "/" + page)
    except Exception as e:
        print("liste alinamadi:", origin + "/" + page, e)
        return []
    paths = list(dict.fromkeys(re.findall(r'href=\\?"(' + prefix + r'[a-z0-9\-]+)\\?"', html)))
    return [(origin + p, p[len(prefix):]) for p in paths]


def page_logo(url):
    """Kanal/mac sayfasindaki site logosu (og:image). Yoksa bos doner."""
    try:
        html = http(url, timeout=10)
        m = re.search(r'og:image"? content="?([^" >]+)', html)
        if m:
            return m.group(1).split("?")[0]
    except Exception:
        pass
    return ""


def b64url(s):
    s = s.replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", errors="replace")


def unpack_numeric(html):
    for m in re.finditer(r'\}\("([A-Za-z]{500,})",(\d+),"([A-Za-z]{5,12})",(\d+),(\d+),(\d+)\)', html):
        try:
            blob, alph, t, e = m.group(1), m.group(3), int(m.group(4)), int(m.group(5))
            if not (2 <= e <= 10 and len(alph) <= 12 and e <= len(alph)):
                continue
            sep = alph[e]
            out = []
            for chunk in blob.split(sep):
                if not chunk:
                    continue
                digits = "".join(str(alph.index(c)) for c in chunk)
                if any(int(d) >= e for d in digits):
                    raise ValueError("taban disi")
                out.append(chr(int(digits, e) - t))
            if len(out) < 100:
                continue
            return "".join(out).encode("latin1").decode("utf-8", errors="replace")
        except Exception:
            continue
    return None


def kpores(embed_html, unpacked, embed_url):
    try:
        base = (re.search(r'<base href="([^"]+)"', embed_html) or [None, None])[1]
        if not base:
            base = embed_url.rsplit("/", 1)[0] + "/"
        purl = re.search(r'EMBD_PLAYERURL\s*=\s*"([^"]+)"', unpacked).group(1)
        sid = re.search(r'EMBD_STREAMID\s*=\s*"([^"]+)"', unpacked).group(1)
        styp = re.search(r'EMBD_STREAMTYPE\s*=\s*"([^"]+)"', unpacked)
        styp = styp.group(1) if styp else "hls"
        fmt = ".mpd" if styp == "dash" else (".mp4" if styp == "mp4" else ".m3u8")
        calls = re.findall(r'\w+\("decrypt",\s*"([^"]{40,})"\)', unpacked)
        cipher = max(calls, key=len)
        fnm = re.search(r'(\w+)\("decrypt",\s*"' + re.escape(cipher) + r'"\)', unpacked).group(1)
        km = re.search(re.escape(fnm) + r'\(\w+,\w+\)\{[\s\S]*?let \w+="([^"]+)";return \w+\+=String\.fromCharCode\(([\d,]+)\),\w+\+"([^"]+)"', unpacked)
        key = km.group(1) + "".join(chr(int(x)) for x in km.group(2).split(",")) + km.group(3)
        raw = base64.b64decode(cipher)
        kb = key.encode("latin1")
        token = "".join(chr(b ^ kb[i % len(kb)]) for i, b in enumerate(raw))
        return base + purl + "?id=" + sid + "&" + token + "&format=" + fmt, embed_url
    except Exception as e:
        print("kpores cozum hatasi:", e)
        return None


def cdnlive(html, page_url):
    if "atob(" not in html:
        return None
    try:
        dec = re.search(r'function\s+(\w+)\(\w+\)[^}]*atob', html).group(1)
        cm = re.search(r'var\s+(\w+)=((?:' + dec + r'\(\w+\)\+)+' + dec + r'\(\w+\))', html)
        parts = re.findall(dec + r'\((\w+)\)', cm.group(2))
        defs = dict(re.findall(r"var (\w+)='([A-Za-z0-9+/=_-]+)'", html))
        stream = "".join(b64url(defs[p]) for p in parts)
        if not stream.startswith("http"):
            return None
        org = urllib.parse.urlparse(page_url)
        return stream, page_url, org.scheme + "://" + org.hostname
    except Exception as e:
        print("cdnlive cozum hatasi:", e)
        return None


def verified(url, referer=None, origin=None):
    try:
        body = http(url, referer, origin).strip()
        return body.startswith("#EXTM3U")
    except Exception:
        return False


def resolve_embed(embed_url, page_url, depth=0):
    if depth > 2:
        return None
    try:
        html = http(embed_url, page_url)
    except Exception:
        return None
    m = re.search(r'(https?://[^\s"\'\\]+?\.m3u8[^\s"\'\\]*)', html)
    if m and verified(m.group(1), embed_url):
        return m.group(1), embed_url, None
    up = unpack_numeric(html)
    if up:
        r = kpores(html, up, embed_url)
        if r and verified(r[0], r[1]):
            return r[0], r[1], None
    try:
        r = cdnlive(html, embed_url)
        if r and verified(r[0], r[1], r[2]):
            return r
    except Exception:
        pass
    for b in dict.fromkeys(re.findall(r'window\.atob\(["\']([^"\']{20,})["\']\)', html)):
        try:
            d = base64.b64decode(b).decode("utf-8", errors="replace")
            mm = re.search(r'(https?://[^\s"\'\\]+?\.m3u8[^\s"\'\\]*)', d)
            if mm and verified(mm.group(1), embed_url):
                return mm.group(1), embed_url, None
        except Exception:
            pass
    for f in dict.fromkeys(re.findall(r'<iframe[^>]+src=["\']([^"\']+)', html)):
        if f.startswith(("data:", "about:", "blob:")) or f == embed_url:
            continue
        r = resolve_embed(urllib.parse.urljoin(embed_url, f), embed_url, depth + 1)
        if r:
            return r
    return None


def resolve_page(page_url):
    try:
        html = http(page_url)
    except Exception as e:
        print("sayfa alinamadi:", page_url, e)
        return None
    m = re.search(r'(https?://[^\s"\'\\]+?\.m3u8[^\s"\'\\]*)', html)
    if m and verified(m.group(1), page_url):
        return m.group(1), page_url, None
    for e in dict.fromkeys(re.findall(r'streamUrl[^a-zA-Z0-9]{0,8}(/api/embed\?u=[A-Za-z0-9_\-]+|https?://[^"\\\s]+)', html)):
        if e in ("$undefined", ""):
            continue
        r = resolve_embed(urllib.parse.urljoin(page_url, e), page_url)
        if r:
            return r
    try:
        r = cdnlive(html, page_url)
        if r and verified(r[0], r[1], r[2]):
            return r
    except Exception:
        pass
    return None


def main():
    origins = resolve_origins()
    if not origins:
        print("HIC CALISAN SITE YOK")
        return
    matches, channels, seen = [], [], set()

    def collect(origin, page, prefix, group, is_channel):
        links = list_links(origin, page, prefix)
        # site logolarini paralel cek
        logos = {}
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            fut = {ex.submit(page_logo, url): url for url, _ in links}
            for f in cf.as_completed(fut):
                try:
                    logos[fut[f]] = f.result()
                except Exception:
                    logos[fut[f]] = ""
        for url, slug in links:
            title = slug_title(slug, keep_numbers=is_channel)
            key = (group, title.lower())
            if key in seen:
                continue
            seen.add(key)
            logo = logos.get(url) or (tr_logo(title) if is_channel else "") or favicon(origin)
            yield url, slug, title, logo, group

    jobs = []
    for key in FAMILY:
        if key not in origins:
            continue
        o = origins[key]
        jobs += list(collect(o, "", "/mac/", "Canlı Maçlar", False))
        jobs += list(collect(o, "kanallar", "/kanal/", "Spor Kanalları", True))
    print("bulunan oge:", len(jobs))

    results = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        fut = {ex.submit(resolve_page, url): (url, slug, title, logo, group) for url, slug, title, logo, group in jobs}
        for f in cf.as_completed(fut):
            url, slug, title, logo, group = fut[f]
            try:
                r = f.result()
            except Exception as e:
                print("cozum exc:", title, e)
                r = None
            if r:
                results.append((group, slug, title, logo, r))
                print("OK:", group, "-", title)
            else:
                print("BOŞ:", group, "-", title)

    results.sort(key=lambda x: (x[0] != "Canlı Maçlar", x[2].lower()))
    kd = os.path.join(OUT_DIR, "kanallar")
    os.makedirs(kd, exist_ok=True)
    for f in os.listdir(kd):  # ölü dosyaları temizle
        if f.endswith(".m3u8"):
            os.remove(os.path.join(kd, f))

    lines = ["#EXTM3U", "# ElmaSpor otomatik liste"]
    for group, slug, title, logo, (stream, ref, org) in results:
        lines.append('#EXTINF:-1 tvg-logo="%s" group-title="%s",%s' % (logo, group, title))
        lines.append("#EXTVLCOPT:http-user-agent=" + UA)
        if ref:
            lines.append("#EXTVLCOPT:http-referrer=" + ref)
        lines.append(stream)
        if group == "Spor Kanalları":
            with open(os.path.join(kd, slug + ".m3u8"), "w") as fh:
                fh.write("#EXTM3U\n#EXTINF:-1 tvg-logo=\"%s\",%s\n" % (logo, title))
                fh.write("#EXTVLCOPT:http-user-agent=" + UA + "\n")
                if ref:
                    fh.write("#EXTVLCOPT:http-referrer=" + ref + "\n")
                fh.write(stream + "\n")
    with open(os.path.join(OUT_DIR, "liste.m3u"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("YAZILDI: %d yayin" % len(results))


if __name__ == "__main__":
    main()
