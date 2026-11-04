#!/usr/bin/env python3
"""Turn the saved Luxury Presence pages into a self-hosted static site.

Usage: python3 -I tools/build.py <mirror_dir> <cache_dir> <out_dir>

mirror_dir  raw server HTML saved from ljresidentialgroup.com (one file per page)
cache_dir   download cache for remote assets (url -> file), reused between runs
out_dir     the static site to publish (Netlify publish directory)
"""
import hashlib, html, json, os, re, shutil, subprocess, sys, urllib.parse

import bs4

MIRROR, CACHE, OUT = sys.argv[1:4]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

PAGES = {  # mirror file -> output path
    "index.html": "index.html",
    "about.html": "about/index.html",
    "services.html": "services/index.html",
    "testimonials.html": "testimonials/index.html",
    "home-valuation.html": "home-valuation/index.html",
    "terms-and-conditions.html": "terms-and-conditions/index.html",
    "sitemap.html": "sitemap/index.html",
    "dmca-notice.html": "dmca-notice/index.html",
    "properties.html": "properties/index.html",
    "privacy-policy.html": "404.html",
    "contactinfo.html": "contactinfo/index.html",
    "qr-contact.html": "qr-contact/index.html",
    "neighborhoods.html": "neighborhoods/index.html",
    "neighborhoods_northwest-hills.html": "neighborhoods/northwest-hills/index.html",
    "neighborhoods_westover-hills.html": "neighborhoods/westover-hills/index.html",  # the live /privacy-policy is the site's 404 page
    "properties_2419-ashley-way-austin-tx-us-78744-7254772.html":
        "properties/2419-ashley-way-austin-tx-us-78744-7254772/index.html",
    "properties_4207-canyonside-trail.html": "properties/4207-canyonside-trail/index.html",
    "properties_4405-tambre-bnd-austin-tx-78738-8821382.html":
        "properties/4405-tambre-bnd-austin-tx-78738-8821382/index.html",
    "properties_9705-mountain-quail-rd-austin-tx-78758-9452890.html":
        "properties/9705-mountain-quail-rd-austin-tx-78758-9452890/index.html",
}

# Hosts whose files get copied into /assets so nothing depends on Luxury Presence.
LOCAL_HOSTS = [
    "media-production.lp-cdn.com", "res.cloudinary.com", "d1e1jt2fj4r8r.cloudfront.net",
    "dq1niho2427i9.cloudfront.net", "dlajgvw9htjpb.cloudfront.net", "styles.luxurypresence.com",
    "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "images.unsplash.com",
    "fonts.googleapis.com", "fonts.gstatic.com",
]
HOST_RE = "|".join(re.escape(h) for h in LOCAL_HOSTS)
# A URL ends at whitespace, quotes, parens, angle brackets, backticks, or an html-escaped quote.
URL_RE = re.compile(r"(?:https?:)?//(?:%s)/(?:(?!&quot;|&#39;|&#x27;)[^\s\"'()<>`\\])*" % HOST_RE)

# Scripts dropped entirely (tracking, consent banner, Cloudflare, translate, LP event bus).
DROP_SCRIPT = re.compile(
    r"lp-consent|utmParse|WidgetTrackerObject|email-decode|googletagmanager|gtm\.start|"
    r"divolteLp=|eventBusLp=|translate\.google|googleTranslateElementInit|__CF\$cv|challenges\.cloudflare")

cache_index_path = os.path.join(CACHE, "index.json")
cache = json.load(open(cache_index_path)) if os.path.exists(cache_index_path) else {}
missing = set()


def fetch(url):
    """Download url into the cache once; return the cached file name or None."""
    if url in cache:
        return cache[url]
    full = "https:" + url if url.startswith("//") else url
    path = urllib.parse.urlparse(full).path
    ext = os.path.splitext(path)[1].lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,5}", ext or ""):
        ext = ""
    key = hashlib.sha1(full.encode()).hexdigest()[:16]
    tmp = os.path.join(CACHE, key + ".part")
    hdr = os.path.join(CACHE, key + ".hdr")
    r = subprocess.run(["curl", "-sS", "-f", "-L", "-m", "120", "-A", UA, "-D", hdr, "-o", tmp, full])
    if r.returncode != 0 or not os.path.getsize(tmp):
        missing.add(full)
        for f in (tmp, hdr):
            if os.path.exists(f):
                os.remove(f)
        return None
    if not ext:  # infer from content type
        ct = re.findall(r"(?im)^content-type:\s*([^;\s]+)", open(hdr, errors="ignore").read())
        ct = ct[-1].lower() if ct else ""
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/avif": ".avif",
               "image/gif": ".gif", "image/svg+xml": ".svg", "text/css": ".css",
               "application/javascript": ".js", "text/javascript": ".js", "font/woff2": ".woff2",
               "font/woff": ".woff", "font/ttf": ".ttf", "video/mp4": ".mp4", "video/webm": ".webm",
               "application/pdf": ".pdf", "image/x-icon": ".ico"}.get(ct, ".bin")
    os.remove(hdr)
    name = key + ext
    os.replace(tmp, os.path.join(CACHE, name))
    cache[url] = name
    return name


def local_url(raw):
    """Map a remote asset URL (as written in source) to its /assets path."""
    url = html.unescape(raw)
    name = fetch(url)
    if not name:
        return raw
    dst = os.path.join(OUT, "assets", name)
    if not os.path.exists(dst):
        src = os.path.join(CACHE, name)
        if name.endswith(".css"):
            css = open(src, encoding="utf-8", errors="ignore").read()
            open(dst, "w").write(rewrite_css(css, url))
        else:
            shutil.copyfile(src, dst)
    return "/assets/" + name


def rewrite_css(css, base):
    """Localize url(...) references inside a stylesheet, resolving relative ones against base."""
    def repl(m):
        ref = m.group(2).strip()
        if ref.startswith("data:") or ref.startswith("#"):
            return m.group(0)
        absu = urllib.parse.urljoin("https:" + base if base.startswith("//") else base, ref)
        if not re.match(r"https?://(%s)/" % HOST_RE, absu):
            return m.group(0)
        return "url(%s%s%s)" % (m.group(1), local_url(absu), m.group(1))
    css = re.sub(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", repl, css)
    css = re.sub(r"@import\s+(['\"])([^'\"]+)\1",
                 lambda m: '@import "%s"' % local_url(m.group(2)) if re.match(URL_RE, m.group(2)) else m.group(0), css)
    return css


def decode_cfemail(hexstr):
    k = int(hexstr[:2], 16)
    return "".join(chr(int(hexstr[i:i + 2], 16) ^ k) for i in range(2, len(hexstr), 2))


# "Lawrence Sternberg" or "LJ Sternberg", but not the already-full Lawrence "LJ" Sternberg.
NAME_RE = re.compile(r'(?<![\w"\u201c\u201d])(?:Lawrence|LJ)\s+Sternberg')

FORM_NAMES = {"NEWSLETTER_SIGNUP": "newsletter", "CONTACT_INQUIRY": "contact", "HOME_VALUATION": "home-valuation"}


def transform(src):
    soup = bs4.BeautifulSoup(src, "html.parser")

    # Cloudflare-obfuscated emails -> plain text / mailto.
    for el in soup.select("[data-cfemail]"):
        el.replace_with(decode_cfemail(el["data-cfemail"]))
    for a in soup.select('a[href*="/cdn-cgi/l/email-protection"]'):
        frag = a["href"].split("#", 1)
        a["href"] = "mailto:" + decode_cfemail(frag[1]) if len(frag) == 2 else "mailto:lj@ljresidentialgroup.com"

    # Links with raw spaces (e.g. the floor-plan PDF) need encoding before the URL regex sees them.
    for a in soup.find_all("a", href=True):
        if " " in a["href"] and re.match(URL_RE, a["href"].replace(" ", "%20")):
            a["href"] = a["href"].replace(" ", "%20")

    # Scripts: drop tracking/consent, keep the site's own behaviour scripts.
    for s in soup.find_all("script"):
        # Only judge small inline snippets; the big LP bundles mention these names but are needed.
        body = s.string or ""
        blob = (s.get("src") or "") + (body if len(body) < 5000 else "")
        if DROP_SCRIPT.search(blob):
            s.decompose()
    for n in soup.find_all("noscript"):
        if "googletagmanager" in str(n):
            n.decompose()
    for f in soup.find_all("iframe"):
        if "googletagmanager" in (f.get("src") or ""):
            f.decompose()

    # Home search is gone: remove nav items and the hero button; neighbourhood cards open Let's Connect.
    for a in soup.select('a[href*="/home-search"]'):
        li = a.find_parent("li")
        if "gallery-card" in (a.get("class") or []):
            a["href"] = "#contact"
            a["data-type"] = "CONTACT_US"
        elif li is not None and len(li.find_all("a")) == 1:
            li.decompose()
        else:
            a.decompose()

    # Lawrence's review (2026-11-04): drop the Oak Mountain test page from the sitemap, the
    # login-only /profile link, and 4207 Canyonside Trail from featured listings.
    for a in soup.select('a[href="/Oakmountain"], a[href="/profile"]'):
        li = a.find_parent("li")
        (li if li is not None and len(li.find_all("a")) == 1 else a).decompose()
    for a in soup.select('.featured-properties a[href*="4207-canyonside-trail"]'):
        item = a.find_parent("li", class_="featured-properties__item-cover")
        if item is not None:
            item.decompose()

    # Sections that only make sense with home search or a Google Maps key: the "Start Your Home
    # Search" banner and the neighborhood map (which would spin forever).
    for sec in soup.select("section[id^=section-]"):
        if sec.select_one(".neighborhood-map") or sec.get_text(" ", strip=True).startswith("Start Your Home Search"):
            sec.decompose()

    # The hero video has no audio track, so its speaker (mute) icon does nothing. Hidden at
    # Lawrence's request (2026-11-04).
    for el in soup.select(".mute-icon__container"):
        el.decompose()

    # "Powered by Luxury Presence" credit.
    for a in soup.select('a[href^="https://www.luxurypresence.com"]'):
        p = a.parent
        if p is not None and "Powered by" in p.get_text():
            p.decompose()
        else:
            a.decompose()

    # Profile-update modal posts to Luxury Presence's lead API only; it has no Netlify equivalent.
    q = soup.find(id="qualifying-questions-modal-form")
    if q is not None:
        modal = q.find_parent(class_="modal") or q.find_parent(id=re.compile("qualifying"))
        (modal or q).decompose()

    # Netlify Forms: name each form by its LP "source" so submissions land in separate inboxes.
    for form in soup.select('form[data-type="contact-form"]'):
        src_in = form.find("input", attrs={"name": "source"})
        name = FORM_NAMES.get(src_in.get("value") if src_in else "", "contact")
        # Netlify keeps only the fields of the first form it sees under a name, so variants with
        # different fields get their own inbox.
        if name == "contact" and form.find(attrs={"name": "tourTime"}):
            name = "schedule-showing"
        elif name == "contact" and not form.find(attrs={"name": "message"}):
            name = "quick-contact"
        form["name"] = name
        form["method"] = "POST"
        form["data-netlify"] = "true"
        form["netlify-honeypot"] = "middleName"
        if not form.find("input", attrs={"name": "form-name"}):
            hidden = soup.new_tag("input", attrs={"type": "hidden", "name": "form-name", "value": name})
            form.insert(0, hidden)

    # Our own form handler + small fixes, loaded before the LP scripts so it wins the submit event.
    head = soup.head
    tag = soup.new_tag("script", src="/js/site.js")
    head.insert(0, tag)

    # Lawrence asked (2026-11-04) that his full name always read Lawrence "LJ" Sternberg.
    # First-name-only uses ("Work With Lawrence") and client quotes stay as written.
    def full_name(text):
        return NAME_RE.sub('Lawrence "LJ" Sternberg', text)
    for node in soup.find_all(string=NAME_RE):
        if node.parent is not None and node.parent.name not in ("script", "style") \
                and not isinstance(node, (bs4.Comment, bs4.Doctype)):
            node.replace_with(full_name(str(node)))
    for el in soup.find_all(True):
        for attr in ("alt", "title", "content", "aria-label", "value", "placeholder"):
            v = el.get(attr)
            if isinstance(v, str) and NAME_RE.search(v):
                el[attr] = full_name(v)

    # Keep canonical/Open Graph URLs absolute (they must name the real domain).
    for el in soup.select('link[rel=canonical], meta[content*="ljresidentialgroup.com"]'):
        for attr in ("href", "content"):
            if el.get(attr):
                el[attr] = el[attr].replace("ljresidentialgroup.com", "@@DOMAIN@@")

    out = str(soup)
    # Absolute links back to the old domain become site-relative.
    out = re.sub(r"https?://(?:www\.)?ljresidentialgroup\.com(?=/|\"|')", "", out)
    # Localize every remote asset URL (attributes, srcset, inline CSS, inline JS strings).
    out = URL_RE.sub(lambda m: local_url(m.group(0)), out)
    out = out.replace("@@DOMAIN@@", "ljresidentialgroup.com")
    # The About page's LinkedIn link was doubled up on the old site.
    out = out.replace("https://www.linkedin.com/in/https://www.linkedin.com/in/lawrencesternberg/",
                      "https://www.linkedin.com/in/ljsternberg/")
    # Services accordion module: self-hosted copy of @10up/component-accordion 2.0.1 (MIT).
    out = re.sub(r"https://cdn\.skypack\.dev/pin/@10up/component-accordion@[^\"']+", "/js/vendor/component-accordion.js", out)
    # Turn off Luxury Presence's analytics event bus and consent banner.
    out = re.sub(r"(setEventBus\(\{\s*enabled:\s*)true", r"\1false", out)
    out = re.sub(r"window\.luxuryPresence\.consent\.initialize\([^;]*\);", "", out)
    return out


HIDDEN_PROPERTIES = {"4207-canyonside-trail"}  # no longer listed (Lawrence, 2026-11-04)


def drop_properties(body, slugs):
    """Remove properties by slug from a recorded Properties API answer and fix the count."""
    data = json.loads(body)
    d = data.get("data") or {}
    if isinstance(d.get("properties"), list):
        d["properties"] = [p for p in d["properties"] if p.get("slug") not in slugs]
        if isinstance(d.get("propertiesCount"), dict):
            d["propertiesCount"]["count"] = len(d["properties"])
    return json.dumps(data)


def build_api(rec_path):
    """Recorded API answers (testimonials, featured properties, ...) replayed by /js/site.js."""
    rec = json.load(open(rec_path))
    out, seen = [], set()
    for r in rec:
        path = urllib.parse.urlparse(r["path"]).path
        if path.startswith("/cdn-cgi") or r["status"] != 200:
            continue
        op = ""
        if r["req"]:
            m = re.search(r"query\s+(\w+)", json.loads(r["req"]).get("query", ""))
            op = m.group(1) if m else "anonymous"
        page = urllib.parse.urlparse(r["page"]).path.rstrip("/") or "/"
        key = (path, op, page)
        if key in seen:
            continue
        seen.add(key)
        body = URL_RE.sub(lambda m: local_url(m.group(0)), r["body"])
        if op == "Properties":
            body = drop_properties(body, HIDDEN_PROPERTIES)
        out.append({"path": path, "op": op, "page": page, "ct": r["ct"], "body": body})
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "data", "api.json"), "w"))


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
    for src, dst in PAGES.items():
        text = open(os.path.join(MIRROR, src), encoding="utf-8").read()
        out = transform(text)
        dpath = os.path.join(OUT, dst)
        os.makedirs(os.path.dirname(dpath), exist_ok=True)
        open(dpath, "w", encoding="utf-8").write(out)
        print("built", dst, file=sys.stderr)
        json.dump(cache, open(cache_index_path, "w"), indent=0)
    build_api(os.path.join(MIRROR, "api-rec.json"))
    for fav in ("favicon.ico", "favicon-16x16.png", "favicon-32x32.png", "favicon-48x48.png"):
        name = fetch("https://ljresidentialgroup.com/" + fav)
        if name:
            shutil.copyfile(os.path.join(CACHE, name), os.path.join(OUT, fav))
    json.dump(cache, open(cache_index_path, "w"), indent=0)
    if missing:
        print("MISSING %d assets:" % len(missing), file=sys.stderr)
        for m in sorted(missing):
            print("  ", m, file=sys.stderr)


if __name__ == "__main__":
    main()
