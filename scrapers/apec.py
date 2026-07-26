import logging
import re
import requests
from urllib.parse import urlencode
from .base import BaseScraper, HEADERS

logger = logging.getLogger(__name__)

_SEARCH_PAGE = "https://www.apec.fr/candidat/recherche-emploi.html/emploi"
_API_URL     = "https://www.apec.fr/cms/webservices/rechercheOffre"

# IDs internes APEC → libellé contrat
_CONTRACT_LABEL = {
    101888: "CDI",
    101887: "CDD",
    101889: "Intérim",
    101890: "Freelance",
    101891: "Alternance",
    101892: "Stage",
}


class ApecScraper(BaseScraper):
    site_name = "APEC"

    def build_url(self, criteria: dict) -> str:
        params = {}
        keywords = criteria.get("keywords", [])
        if keywords:
            params["motsCles"] = " ".join(keywords)
        location = (criteria.get("location") or "").strip()
        if location:
            params["lieu"] = location
        return _SEARCH_PAGE + "?" + urlencode(params)

    def fetch_listings(self, criteria: dict) -> list[dict]:
        session = requests.Session()
        hdrs = {**HEADERS, "Referer": "https://www.apec.fr/"}

        # Récupère les cookies DataDome depuis la page de recherche
        session.get(_SEARCH_PAGE, headers=hdrs, timeout=15)

        payload = self._build_payload(criteria)
        api_hdrs = {
            **hdrs,
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.apec.fr",
            "Referer": _SEARCH_PAGE,
        }

        resp = session.post(_API_URL, json=payload, headers=api_hdrs, timeout=15)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code} — APEC a refusé la requête")

        annonces = resp.json().get("resultats") or []
        return [self._parse_offre(a) for a in annonces if a]

    def _build_payload(self, criteria: dict) -> dict:
        payload: dict = {
            "typesConvention": [],   # vide = tous les types de contrat
            "secteursActivite": [],
            "pagination": {"startIndex": 0, "range": 50},
        }
        keywords = criteria.get("keywords", [])
        if keywords:
            payload["motsCles"] = " ".join(keywords)
        return payload

    def _parse_offre(self, o: dict) -> dict:
        num = str(o.get("numeroOffre") or o.get("id") or "")
        url = f"{_SEARCH_PAGE}/detail-offre/{num}" if num else ""

        contract_id = o.get("typeContrat")
        contrat = _CONTRACT_LABEL.get(contract_id, "")

        location = o.get("lieuTexte") or ""
        salaire  = o.get("salaireTexte") or ""

        remote = ""
        tl = str(o.get("idNomTeletravail") or "").lower()
        if "total" in tl or "complet" in tl:
            remote = "100% télétravail"
        elif "partiel" in tl or "occasionnel" in tl:
            remote = "Télétravail partiel"
        elif tl and tl not in ("non", "false", ""):
            remote = "Télétravail"

        desc = o.get("texteOffre") or ""
        desc = re.sub(r"<[^>]+>", " ", desc).strip()
        desc = re.sub(r"\s+", " ", desc)[:500]

        pub_date = (o.get("datePublication") or o.get("dateValidation") or "")[:10]

        return self.normalize({
            "external_id":   num,
            "title":         o.get("intitule", ""),
            "company":       o.get("nomCommercial", ""),
            "contract_type": contrat,
            "location":      location,
            "remote":        remote,
            "salary":        salaire,
            "url":           url,
            "description":   desc,
            "pub_date":      pub_date,
        })
