import logging
import re
import json
import requests as std_requests
from datetime import datetime
from urllib.parse import urlencode
from curl_cffi import requests as cffi_requests
from .base import BaseScraper, HEADERS

logger = logging.getLogger(__name__)

_BASE_URL         = "https://fr.indeed.com"
_SEARCH_URL       = f"{_BASE_URL}/emplois"
_INDEED_HOME      = f"{_BASE_URL}/"
_FLARESOLVERR_URL = __import__("os").getenv("FLARESOLVERR_URL", "http://localhost:8191/v1")

_KM_TO_MILES = {25: 15, 50: 25, 75: 50, 100: 50, 150: 100}

_CONTRACT_CODE = {
    "cdi":        "fulltime",
    "cdd":        "contract",
    "intérim":    "temporary",
    "interim":    "temporary",
    "stage":      "internship",
    "alternance": "internship",
}

# Cache session FlareSolverr : (cookies_dict, user_agent)
_fs_cache: dict = {}


def _get_cloudflare_cookies() -> tuple[dict, str]:
    """Obtient les cookies Cloudflare via FlareSolverr."""
    try:
        resp = std_requests.post(
            _FLARESOLVERR_URL,
            json={"cmd": "request.get", "url": _INDEED_HOME, "maxTimeout": 120000},
            timeout=150,
        )
    except std_requests.exceptions.ConnectionError:
        raise Exception(
            "FlareSolverr inaccessible — lance-le avec : "
            "docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest"
        )

    data = resp.json()
    if data.get("status") != "ok":
        raise Exception(f"FlareSolverr : {data.get('message', 'erreur inconnue')}")

    solution = data["solution"]
    cookies = {c["name"]: c["value"] for c in solution.get("cookies", [])}
    user_agent = solution.get("userAgent", HEADERS["User-Agent"])
    logger.info("Cookies Cloudflare obtenus via FlareSolverr (cf_clearance: %s)", bool(cookies.get("cf_clearance")))
    return cookies, user_agent


def _cached_cookies() -> tuple[dict, str]:
    """Retourne les cookies en cache ou en obtient de nouveaux."""
    if _fs_cache.get("cookies", {}).get("cf_clearance"):
        return _fs_cache["cookies"], _fs_cache["user_agent"]
    cookies, ua = _get_cloudflare_cookies()
    _fs_cache["cookies"] = cookies
    _fs_cache["user_agent"] = ua
    return cookies, ua


def _invalidate_cache():
    _fs_cache.clear()


class IndeedScraper(BaseScraper):
    site_name = "Indeed"

    def build_url(self, criteria: dict) -> str:
        return _SEARCH_URL + "?" + urlencode(self._search_params(criteria))

    def _search_params(self, criteria: dict) -> dict:
        params = {}
        keywords = self._effective_keywords(criteria)
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

    def verify_alive(self, url: str) -> bool | None:
        try:
            cookies, ua = _cached_cookies()
            if not cookies.get("cf_clearance"):
                return None
            resp = cffi_requests.get(url, cookies=cookies, impersonate="chrome", timeout=10)
            if resp.status_code == 404:
                return False
            gone_markers = [
                "cette offre n'est plus disponible",
                "job is no longer available",
                "offre expirée",
                "cette annonce a expiré",
            ]
            return not any(m in resp.text.lower() for m in gone_markers)
        except Exception:
            return None

    def fetch_listings(self, criteria: dict) -> list[dict]:
        cookies, ua = _cached_cookies()
        hdrs = {**HEADERS, "User-Agent": ua}

        results = []
        params = self._search_params(criteria)

        for page_start in (0, 15, 30, 45, 60):
            params["start"] = page_start
            try:
                resp = cffi_requests.get(
                    _SEARCH_URL,
                    params=params,
                    cookies=cookies,
                    headers=hdrs,
                    impersonate="chrome",
                    timeout=15,
                )
                if resp.status_code == 403:
                    # Cookie expiré → renouvelle via FlareSolverr et réessaie
                    _invalidate_cache()
                    cookies, ua = _cached_cookies()
                    hdrs["User-Agent"] = ua
                    resp = cffi_requests.get(
                        _SEARCH_URL, params=params, cookies=cookies,
                        headers=hdrs, impersonate="chrome", timeout=15,
                    )
                    if resp.status_code == 403:
                        raise Exception("Indeed bloque la requête même après renouvellement des cookies FlareSolverr.")

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

        create_ts = item.get("createDate")
        pub_date = datetime.utcfromtimestamp(create_ts / 1000).strftime("%Y-%m-%d") if create_ts else ""

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
