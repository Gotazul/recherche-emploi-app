import logging
import re
import requests
from curl_cffi import requests as cffi_requests
from urllib.parse import urlencode
from .base import BaseScraper, HEADERS

logger = logging.getLogger(__name__)

_BASE_URL      = "https://www.welcometothejungle.com"
_ENV_URL       = f"{_BASE_URL}/api/env"
_ALGOLIA_INDEX = "wk_cms_jobs_production"

# Mapping WTTJ contract_type → label français
_CONTRACT_FR = {
    "FULL_TIME":    "CDI",
    "PART_TIME":    "Temps partiel",
    "TEMPORARY":    "CDD",
    "FREELANCE":    "Freelance",
    "INTERNSHIP":   "Stage",
    "APPRENTICESHIP": "Alternance",
    "ALTERNATION":  "Alternance",
    "VOLUNTEER":    "Bénévolat",
}

_REMOTE_FR = {
    "remote":      "100% télétravail",
    "full":        "100% télétravail",
    "partial":     "Télétravail partiel",
    "punctual":    "Télétravail partiel",
    "no_remote":   "",
    "none":        "",
    "unknown":     "",
}

_algolia_cache: dict = {}


def _get_algolia_config() -> tuple[str, str]:
    if _algolia_cache:
        return _algolia_cache["app_id"], _algolia_cache["api_key"]
    try:
        r = cffi_requests.get(_ENV_URL, impersonate="chrome", timeout=10)
        m = re.search(r'"PUBLIC_ALGOLIA_APPLICATION_ID":"([^"]+)"', r.text)
        k = re.search(r'"PUBLIC_ALGOLIA_API_KEY_CLIENT":"([^"]+)"', r.text)
        if m and k:
            _algolia_cache["app_id"] = m.group(1)
            _algolia_cache["api_key"] = k.group(1)
            return _algolia_cache["app_id"], _algolia_cache["api_key"]
    except Exception as e:
        logger.warning("Impossible de récupérer la config Algolia WTTJ: %s", e)
    # Valeurs de secours (peuvent changer si WTTJ les renouvelle)
    return "CSEKHVMS53", "4bd8f6215d0cc52b26430765769e65a0"


class WttjScraper(BaseScraper):
    site_name = "Welcome to the Jungle"

    def build_url(self, criteria: dict) -> str:
        params = {}
        keywords = criteria.get("keywords", [])
        if keywords:
            params["query"] = " ".join(keywords)
        location = (criteria.get("location") or "").strip()
        if location:
            params["aroundQuery"] = location
        return f"{_BASE_URL}/fr/jobs?" + urlencode(params)

    def fetch_listings(self, criteria: dict) -> list[dict]:
        app_id, api_key = _get_algolia_config()
        algolia_url = f"https://{app_id}-dsn.algolia.net/1/indexes/{_ALGOLIA_INDEX}/query"

        hdrs = {
            **HEADERS,
            "X-Algolia-Application-Id": app_id,
            "X-Algolia-API-Key": api_key,
            "Content-Type": "application/json",
            "Referer": _BASE_URL + "/",
            "Origin": _BASE_URL,
        }

        keywords = criteria.get("keywords", [])
        query = " ".join(keywords) if keywords else ""

        # Détermine si on filtre sur les postes juniors/débutants
        # Priorité : champ experience_levels, sinon détection via mots-clés
        _junior_levels = {"junior", "débutant", "debutant"}
        _junior_kw     = {"junior", "débutant", "debutant", "entry", "entrée", "entree"}
        exp_levels = criteria.get("experience_levels") or []
        if exp_levels:
            is_junior = any(e.lower() in _junior_levels for e in exp_levels)
        else:
            is_junior = any(k.lower() in _junior_kw for k in keywords)

        # optionalWords : les termes de niveau d'expérience boostent sans bloquer
        _exp_kw_all = _junior_kw | {
            "senior", "confirmé", "confirme", "intermédiaire", "intermediaire",
            "expérimenté", "experimente",
        }
        optional = [w for w in keywords if w.lower() in _exp_kw_all]

        seen_ids: set[str] = set()
        results = []

        # Filtre expérience : <= 3 (intermédiaire inclus) pour junior, sinon pas de filtre
        base_filter = "website.reference:wttj_fr"
        filters = f"{base_filter} AND experience_level_minimum <= 3" if is_junior else base_filter

        for page in range(5):  # 5 pages × 30 = 150 offres max
            payload = {
                "query": query,
                "hitsPerPage": 30,
                "page": page,
                "filters": filters,
            }
            if optional:
                payload["optionalWords"] = optional

            resp = cffi_requests.post(algolia_url, headers=hdrs, json=payload, impersonate="chrome", timeout=15)
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code} — Algolia WTTJ a refusé la requête")

            data = resp.json()
            for h in data.get("hits", []):
                oid = str(h.get("objectID", ""))
                if oid not in seen_ids:
                    seen_ids.add(oid)
                    results.append(self._parse_hit(h))

            nb_pages = data.get("nbPages", 1)
            if page + 1 >= nb_pages:
                break

        return results

    def _parse_hit(self, h: dict) -> dict:
        org_slug = (h.get("organization") or {}).get("slug", "")
        job_slug = h.get("slug", "")
        url = f"{_BASE_URL}/fr/companies/{org_slug}/jobs/{job_slug}" if org_slug and job_slug else ""

        # Contrat : préférer le libellé FR fourni par l'API
        contract_fr = (h.get("contract_type_names") or {}).get("fr", "")
        if not contract_fr:
            contract_fr = _CONTRACT_FR.get(h.get("contract_type", ""), "")

        # Localisation
        office = h.get("office") or {}
        city = office.get("city", "")
        state = office.get("state", "")
        location = f"{city} ({state})" if city and state else city or state

        # Télétravail
        remote_raw = (h.get("remote") or "").lower()
        remote = _REMOTE_FR.get(remote_raw, "Télétravail" if remote_raw and remote_raw not in ("unknown",) else "")

        # Salaire
        sal_min = h.get("salary_minimum")
        sal_max = h.get("salary_maximum")
        sal_cur = h.get("salary_currency") or "€"
        sal_per = h.get("salary_period") or ""
        if sal_min and sal_max:
            salary = f"{sal_min:,} – {sal_max:,} {sal_cur}"
        elif sal_min:
            salary = f"À partir de {sal_min:,} {sal_cur}"
        else:
            salary = ""
        if salary and sal_per and sal_per != "none":
            salary += f" / {sal_per}"

        pub_date = (h.get("published_at") or "")[:10]

        return self.normalize({
            "external_id":   str(h.get("objectID", "")),
            "title":         h.get("name", ""),
            "company":       (h.get("organization") or {}).get("name", ""),
            "contract_type": contract_fr,
            "location":      location,
            "remote":        remote,
            "salary":        salary,
            "url":           url,
            "description":   "",
            "pub_date":      pub_date,
        })
