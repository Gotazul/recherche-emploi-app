import logging
import re
import subprocess
import time
import xml.etree.ElementTree as ET
import requests
from urllib.parse import urlencode
from .base import BaseScraper, HEADERS

logger = logging.getLogger(__name__)

_RSS_URL     = "https://fr.indeed.com/rss"
_INDEED_HOME = "https://fr.indeed.com/"

_KM_TO_MILES = {25: 15, 50: 25, 75: 50, 100: 50, 150: 100}

_CONTRACT_CODE = {
    "cdi":        "fulltime",
    "cdd":        "contract",
    "intérim":    "temporary",
    "interim":    "temporary",
    "stage":      "internship",
    "alternance": "internship",
}


def _open_chrome_for_cookie():
    """Ouvre un onglet Chrome sur Indeed pour rafraîchir le cookie DataDome."""
    for cmd in (
        ["google-chrome", "--new-tab", _INDEED_HOME],
        ["google-chrome-stable", "--new-tab", _INDEED_HOME],
        ["chromium-browser", "--new-tab", _INDEED_HOME],
        ["xdg-open", _INDEED_HOME],
    ):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(5)
            return
        except FileNotFoundError:
            continue


def _read_chrome_cookies() -> dict:
    try:
        import rookiepy
        cj = rookiepy.chrome([".indeed.com"])
        return {c["name"]: c["value"] for c in cj}
    except Exception as e:
        logger.warning("rookiepy ne peut pas lire les cookies Chrome Indeed : %s", e)
        return {}


class IndeedScraper(BaseScraper):
    site_name = "Indeed"

    def build_url(self, criteria: dict) -> str:
        return "https://fr.indeed.com/emplois?" + urlencode(self._search_params(criteria))

    def _search_params(self, criteria: dict) -> dict:
        params = {}
        keywords = criteria.get("keywords", [])
        if keywords:
            params["q"] = " ".join(keywords)

        location = (criteria.get("location") or "").strip()
        if location:
            params["l"] = location

        radius_km = criteria.get("radius_km")
        if radius_km:
            miles = min(_KM_TO_MILES.items(), key=lambda x: abs(x[0] - radius_km))[1]
            params["radius"] = miles

        contracts = criteria.get("contract_types", [])
        codes = list(dict.fromkeys(
            _CONTRACT_CODE[c.lower()] for c in contracts if c.lower() in _CONTRACT_CODE
        ))
        if len(codes) == 1:
            params["jt"] = codes[0]

        return params

    def fetch_listings(self, criteria: dict) -> list[dict]:
        _open_chrome_for_cookie()
        cookies = _read_chrome_cookies()

        if not cookies.get("datadome"):
            raise Exception(
                "Cookie DataDome absent — assure-toi que Chrome est installé "
                "et que tu t'es connecté à fr.indeed.com au moins une fois."
            )

        hdrs = {
            **HEADERS,
            "Referer": _INDEED_HOME,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
        rss_params = {**self._search_params(criteria), "lang": "fr"}
        resp = requests.get(_RSS_URL, params=rss_params, headers=hdrs, cookies=cookies, timeout=15)

        if resp.status_code == 403:
            raise Exception(
                "Indeed bloque la requête malgré le cookie Chrome. "
                "Clique sur 'Ouvrir' pour consulter les offres manuellement."
            )
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code} — Indeed a refusé la requête")

        return self._parse_rss(resp.text)

    def _parse_rss(self, xml_text: str) -> list[dict]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            raise Exception(f"Réponse RSS invalide (protection anti-bot probable) : {e}")

        items = root.findall(".//item")
        if not items:
            return []

        results = []
        for item in items:
            try:
                results.append(self._parse_item(item))
            except Exception:
                continue
        return results

    def _parse_item(self, item) -> dict:
        def text(tag):
            el = item.find(tag)
            return el.text.strip() if el is not None and el.text else ""

        title_raw = text("title")
        url       = text("link")
        desc_raw  = text("description")
        pub_date  = text("pubDate")[:10] if text("pubDate") else ""

        # Indeed RSS : "Titre - Entreprise - Ville" dans <title>
        title, company, location = title_raw, "", ""
        parts = [p.strip() for p in title_raw.split(" - ")]
        if len(parts) >= 3:
            title, company, location = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            title, company = parts[0], parts[1]

        ext_id_m = re.search(r"jk=([a-z0-9]+)", url)
        ext_id = ext_id_m.group(1) if ext_id_m else url

        description = re.sub(r"<[^>]+>", " ", desc_raw).strip()
        description = re.sub(r"\s+", " ", description)[:500]

        remote = ""
        desc_lower = description.lower()
        if "100% télétravail" in desc_lower or "full remote" in desc_lower:
            remote = "100% télétravail"
        elif "télétravail" in desc_lower or "remote" in desc_lower:
            remote = "Télétravail partiel"

        return self.normalize({
            "external_id": ext_id,
            "title":       title,
            "company":     company,
            "location":    location,
            "remote":      remote,
            "url":         url,
            "description": description,
            "pub_date":    pub_date,
        })
