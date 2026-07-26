import logging
import re
import subprocess
import time
import json
from datetime import datetime
from urllib.parse import urlencode
from .base import BaseScraper, HEADERS

logger = logging.getLogger(__name__)

_BASE_URL    = "https://fr.indeed.com"
_SEARCH_URL  = f"{_BASE_URL}/emplois"
_INDEED_HOME = f"{_BASE_URL}/"

_KM_TO_MILES = {25: 15, 50: 25, 75: 50, 100: 50, 150: 100}

_CONTRACT_CODE = {
    "cdi":        "fulltime",
    "cdd":        "contract",
    "intérim":    "temporary",
    "interim":    "temporary",
    "stage":      "internship",
    "alternance": "internship",
}


def _open_browser_and_close(wait: int = 10):
    """Ouvre Indeed dans un nouvel onglet, attend le chargement, ferme l'onglet."""
    for cmd in (
        ["google-chrome", "--new-tab", _INDEED_HOME],
        ["google-chrome-stable", "--new-tab", _INDEED_HOME],
        ["chromium-browser", "--new-tab", _INDEED_HOME],
        ["firefox", "--new-tab", _INDEED_HOME],
        ["xdg-open", _INDEED_HOME],
    ):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(wait)
            # Ferme l'onglet actif via xdotool si disponible
            try:
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", "ctrl+w"],
                    timeout=2, capture_output=True
                )
            except Exception:
                pass
            return
        except FileNotFoundError:
            continue


def _read_browser_cookies() -> dict:
    import rookiepy
    domain = [".indeed.com"]
    for reader, name in (
        (rookiepy.chrome,   "Chrome"),
        (rookiepy.chromium, "Chromium"),
        (rookiepy.firefox,  "Firefox"),
    ):
        try:
            cj = reader(domain)
            cookies = {c["name"]: c["value"] for c in cj}
            if cookies.get("cf_clearance"):
                logger.info("Cookies Cloudflare lus depuis %s", name)
                return cookies
        except Exception as e:
            logger.debug("%s cookies: %s", name, e)
    return {}


class IndeedScraper(BaseScraper):
    site_name = "Indeed"

    def build_url(self, criteria: dict) -> str:
        return _SEARCH_URL + "?" + urlencode(self._search_params(criteria))

    def _search_params(self, criteria: dict) -> dict:
        params = {}
        keywords = criteria.get("keywords", [])
        if keywords:
            params["q"] = " ".join(keywords)

        location = (criteria.get("location") or "").strip()
        params["l"] = location or "France"

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
        from curl_cffi import requests as cffi_requests

        # Utilise les cookies existants ; n'ouvre le navigateur que si absent ou expiré
        cookies = _read_browser_cookies()
        if not cookies.get("cf_clearance"):
            _open_browser_and_close(wait=10)
            cookies = _read_browser_cookies()
            if not cookies.get("cf_clearance"):
                raise Exception(
                    "Cookie Cloudflare absent — visite fr.indeed.com dans Chrome ou Firefox "
                    "et relance la recherche (pas besoin de compte)."
                )

        results = []
        params = self._search_params(criteria)

        for page_start in (0, 15, 30, 45, 60):
            params["start"] = page_start
            try:
                resp = cffi_requests.get(
                    _SEARCH_URL,
                    params=params,
                    cookies=cookies,
                    impersonate="chrome",
                    timeout=15,
                )
                if resp.status_code == 403:
                    # Cookie expiré → rafraîchit et réessaie une fois
                    _open_browser_and_close(wait=10)
                    cookies = _read_browser_cookies()
                    resp = cffi_requests.get(
                        _SEARCH_URL, params=params, cookies=cookies,
                        impersonate="chrome", timeout=15,
                    )
                    if resp.status_code == 403:
                        raise Exception(
                            "Indeed bloque la requête même après rafraîchissement. "
                            "Visite fr.indeed.com manuellement et relance."
                        )
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code} — Indeed a refusé la requête")

                page_results = self._parse_html(resp.text)
                results.extend(page_results)
                if len(page_results) < 15:
                    break
            except Exception:
                if page_start == 0:
                    raise
                break

        return results

    def _parse_html(self, html: str) -> list[dict]:
        m = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});\s*window\.mosaic',
            html, re.S
        )
        if not m:
            raise Exception("Impossible de parser les offres Indeed (structure HTML modifiée)")

        data = json.loads(m.group(1))
        raw = (
            data.get("metaData", {})
                .get("mosaicProviderJobCardsModel", {})
                .get("results", [])
        )
        listings = []
        for item in raw:
            try:
                listings.append(self._parse_item(item))
            except Exception:
                continue
        return listings

    def _parse_item(self, item: dict) -> dict:
        job_key = item.get("jobkey", "")
        url = f"{_BASE_URL}/viewjob?jk={job_key}" if job_key else ""

        salary_obj = item.get("salarySnippet") or {}
        salary = salary_obj.get("text", "")

        contract_types = item.get("jobTypes") or []
        contract_type = ", ".join(contract_types) if contract_types else ""

        # Timestamp ms → date YYYY-MM-DD
        create_ts = item.get("createDate")
        if create_ts:
            pub_date = datetime.utcfromtimestamp(create_ts / 1000).strftime("%Y-%m-%d")
        else:
            pub_date = ""

        snippet_html = item.get("snippet", "")
        description = re.sub(r"<[^>]+>", " ", snippet_html).strip()
        description = re.sub(r"\s+", " ", description)[:500]

        remote = ""
        desc_lower = description.lower()
        title_lower = (item.get("displayTitle") or "").lower()
        if "100% télétravail" in desc_lower or "full remote" in desc_lower:
            remote = "100% télétravail"
        elif "télétravail" in desc_lower or "remote" in desc_lower or "télétravail" in title_lower:
            remote = "Télétravail partiel"

        return self.normalize({
            "external_id":   job_key,
            "title":         item.get("displayTitle", ""),
            "company":       item.get("company", ""),
            "contract_type": contract_type,
            "location":      item.get("formattedLocation", ""),
            "remote":        remote,
            "salary":        salary,
            "url":           url,
            "description":   description,
            "pub_date":      pub_date,
        })
