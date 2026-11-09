#!/usr/bin/env python3
"""Ustvari sitemap.xml za Sidebit iz javnih HTML-datotek v projektu.

Uporaba: python3 generate_sitemap.py [pot-do-javne-mape]
Pregleda HTML v korenu javne mape in v orodja/ (tudi v podmapah).
Za ročne izjeme dodaj --exclude orodja/ime.html; možnost lahko ponoviš.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit

SITE = "https://sidebit.si"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SKIP = {"404.html", "500.html", "offline.html"}


class PageHead(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonicals = set()
        self.skip = False

    def handle_starttag(self, tag, attrs):
        attrs = {key: value or "" for key, value in attrs}
        if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
            if attrs.get("href", "").strip():
                self.canonicals.add(attrs["href"].strip())
        if tag == "meta":
            name = attrs.get("name", "").strip().lower()
            directives = re.split(r"[\s,;]+", attrs.get("content", "").lower())
            if name in {"robots", "googlebot"} and {"noindex", "none"}.intersection(directives):
                self.skip = True
            if attrs.get("http-equiv", "").strip().lower() == "refresh":
                self.skip |= bool(re.search(r"\burl\s*=", attrs.get("content", ""), re.I))


def public_url(relative):
    if relative.name == "index.html":
        parent = relative.parent.as_posix()
        return SITE + ("/" if parent == "." else "/" + quote(parent) + "/")
    return SITE + "/" + quote(relative.as_posix())


def canonical_url(url, canonical):
    parts = urlsplit(urljoin(url, canonical))
    if parts.scheme != "https" or parts.netloc.lower() != "sidebit.si" or parts.query:
        return None
    path = quote(unquote(parts.path or "/"))
    if path.endswith("/index.html"):
        path = path[:-len("index.html")]
    return SITE + path


def collect(root, excludes):
    urls = set()
    for page in sorted([*root.glob("*.html"), *(root / "orodja").rglob("*.html")]):
        rel = page.relative_to(root)
        if (not page.is_file() or not page.resolve().is_relative_to(root)
                or page.name.lower() in SKIP or rel.as_posix() in excludes
                or any(part.startswith(".") for part in rel.parts)):
            continue
        head = PageHead()
        # Predloge Sidebit uporabljajo UTF-8; BOM je dovoljen.
        html = page.read_text(encoding="utf-8-sig")
        head.feed(re.split(r"</head\s*>", html, maxsplit=1, flags=re.I)[0])
        head.close()
        if head.skip:
            continue
        url = public_url(rel)
        if head.canonicals:
            targets = {canonical_url(url, target) for target in head.canonicals}
            if targets != {url}:
                print(f"Izpuščen {rel.as_posix()}: drug ali neveljaven canonical.", file=sys.stderr)
                continue
        urls.add(url)
    return sorted(urls)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=".", help="Mapa z javnima index.html in orodja/")
    parser.add_argument("--exclude", action="append", default=[], metavar="POT")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not (root / "index.html").is_file() or not (root / "orodja").is_dir():
        parser.error("V izbrani mapi morata biti index.html in mapa orodja/.")
    urls = collect(root, set(args.exclude))
    if not urls:
        parser.error("Ni URL-jev za vključitev.")
    if len(urls) > 50000:
        parser.error("Več kot 50.000 URL-jev: sitemap je treba razdeliti.")
    xml = ET.Element("urlset", xmlns=NS)
    for url in urls:
        ET.SubElement(ET.SubElement(xml, "url"), "loc").text = url
    ET.indent(xml, space="  ")
    data = ET.tostring(xml, encoding="utf-8", xml_declaration=True) + b"\n"
    if len(data) > 50 * 1024 * 1024:
        parser.error("XML presega omejitev 50 MiB.")
    target = root / "sitemap.xml"
    target.write_bytes(data)
    print(f"{target}: {len(urls)} URL-jev.")


if __name__ == "__main__":
    main()
