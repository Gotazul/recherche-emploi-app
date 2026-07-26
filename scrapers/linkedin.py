import logging
import re
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from .base import BaseScraper

logger = logging.getLogger(__name__)

_BASE_URL   = "https://www.linkedin.com"
_GUEST_API  = f"{_BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search"
_SEARCH_URL = f"{_BASE_URL}/jobs/search/"

# f_E : niveaux d'expérience LinkedIn
# 1=Débutant, 2=Associé, 3=Intermédiaire, 4=Senior, 5=Directeur, 6=Exécutif
_JUNIOR_EXP_FILTER = "1,2"

# f_JT : types de contrat LinkedIn
_CONTRACT_MAP = {
    "cdi":        "F",   # Full-time
    "cdd":        "C",   # Contract
    "intérim":    "T",   # Temporary
    "interim":    "T",
    "freelance":  "F",
    "alternance": "I",   # Internship
    "stage":      "I",
}

# Mapping niveau d'expérience → codes LinkedIn f_E
_EXPERIENCE_CODES = {
    "débutant":      "1",
    "junior":        "2",
    "intermédiaire": "3",
    "senior":        "4",
}
_JUNIOR_KW = {"junior", "débutant", "debutant", "entry", "entrée", "entree"}


class LinkedInScraper(BaseScraper):
    site_name = "LinkedIn"

    def build_url(self, criteria: dict) -> str:
        params = {"keywords": " ".join(criteria.get("keywords", [])),
                  "location": criteria.get("location") or "France"}
        return _SEARCH_URL + "?" + urlencode(params)

    def _search_params(self, criteria: dict) -> dict:
        keywords = criteria.get("keywords", [])
        params = {
            "keywords": " ".join(keywords),
            "location": criteria.get("location") or "France",
            "geoId":    "105015875",  # France
        }

        # Filtre niveau d'expérience : champ dédié en priorité, sinon détection via mots-clés
        exp_levels = criteria.get("experience_levels") or []
        if exp_levels:
            codes = [_EXPERIENCE_CODES[e] for e in exp_levels if e in _EXPERIENCE_CODES]
            if codes:
                params["f_E"] = ",".join(codes)
        elif any(k.lower() in _JUNIOR_KW for k in keywords):
            params["f_E"] = _JUNIOR_EXP_FILTER

        # Filtre type de contrat (seulement si un seul type demandé)
        contracts = criteria.get("contract_types", [])
        codes = list(dict.fromkeys(
            _CONTRACT_MAP[c.lower()] for c in contracts if c.lower() in _CONTRACT_MAP
        ))
        if len(codes) == 1:
            params["f_JT"] = codes[0]

        return params

    def fetch_listings(self, criteria: dict) -> list[dict]:
        params = self._search_params(criteria)
        results = []
        seen_ids: set[str] = set()

        for page_start in range(0, 75, 25):  # 3 pages × 25 = 75 offres max
            params["start"] = page_start
            try:
                resp = cffi_requests.get(
                    _GUEST_API, params=params, impersonate="chrome", timeout=15
                )
                if resp.status_code == 400:
                    # LinkedIn renvoie 400 quand il n'y a plus de résultats
                    break
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code} — LinkedIn a refusé la requête")

                cards = self._parse_html(resp.text)
                if not cards:
                    break
                for card in cards:
                    if card["external_id"] not in seen_ids:
                        seen_ids.add(card["external_id"])
                        results.append(card)

            except Exception:
                if page_start == 0:
                    raise
                break

        return results

    def _parse_html(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.find_all("div", class_="base-search-card")
        return [self._parse_card(c) for c in cards if c.get("data-entity-urn")]

    def _parse_card(self, card) -> dict:
        job_id = card.get("data-entity-urn", "").split(":")[-1]

        title_el   = card.find("h3", class_="base-search-card__title")
        company_el = card.find("h4", class_="base-search-card__subtitle")
        loc_el     = card.find("span", class_="job-search-card__location")
        date_el    = card.find("time")
        link_el    = card.find("a", class_="base-card__full-link")

        title    = title_el.get_text(strip=True)   if title_el   else ""
        company  = company_el.get_text(strip=True) if company_el else ""
        location = loc_el.get_text(strip=True)     if loc_el     else ""
        pub_date = date_el.get("datetime", "")[:10] if date_el   else ""
        url      = link_el["href"].split("?")[0]   if link_el    else ""

        return self.normalize({
            "external_id": job_id,
            "title":       title,
            "company":     company,
            "location":    location,
            "url":         url,
            "pub_date":    pub_date,
        })
