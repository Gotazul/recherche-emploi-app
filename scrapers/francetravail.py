import logging
import os
import time
import requests
from urllib.parse import urlencode
from .base import BaseScraper, HEADERS

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
_SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
_SCOPE = "api_offresdemploiv2 o2dsoffre"

# Mapping type de contrat critère → code API France Travail
_CONTRACT_CODE = {
    "cdi":        "CDI",
    "cdd":        "CDD",
    "intérim":    "MIS",
    "interim":    "MIS",
    "freelance":  "LIB",
    "alternance": "CFA",
    "stage":      "STA",
}

_token_cache: dict = {}  # {"token": ..., "expires_at": ...}


def _get_token(client_id: str, client_secret: str) -> str:
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now + 30:
        return _token_cache["token"]

    resp = requests.post(
        _TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type":    "client_credentials",
            "client_id":     client_id,
            "client_secret": client_secret,
            "scope":         _SCOPE,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 1500)
    return _token_cache["token"]


class FranceTravailScraper(BaseScraper):
    site_name = "France Travail"

    def build_url(self, criteria: dict) -> str:
        params = self._build_params(criteria)
        return f"https://www.francetravail.fr/emploi/nos-offres/rechercher-une-offre?{urlencode(params)}"

    def _build_params(self, criteria: dict) -> dict:
        params = {}

        keywords = criteria.get("keywords", [])
        if keywords:
            params["motsCles"] = " ".join(keywords)

        zip_code = str(criteria.get("location", "") or "").strip()
        if zip_code and zip_code[:2].isdigit():
            dept = zip_code[:2]
            if dept not in ("2A", "2B"):
                params["departement"] = dept

        radius = criteria.get("radius_km")
        if radius:
            params["distance"] = radius

        contracts = criteria.get("contract_types", [])
        codes = [_CONTRACT_CODE.get(c.lower()) for c in contracts if _CONTRACT_CODE.get(c.lower())]
        if codes:
            params["typeContrat"] = ",".join(codes)

        params["range"] = "0-149"
        return params

    def fetch_listings(self, criteria: dict) -> list[dict]:
        client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID", "").strip()
        client_secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise Exception(
                "Credentials manquants — définis FRANCE_TRAVAIL_CLIENT_ID et "
                "FRANCE_TRAVAIL_CLIENT_SECRET dans le fichier .env"
            )

        token = _get_token(client_id, client_secret)
        params = self._build_params(criteria)

        resp = requests.get(
            _SEARCH_URL,
            headers={
                **HEADERS,
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            params=params,
            timeout=15,
        )

        if resp.status_code == 204:
            return []
        resp.raise_for_status()

        data = resp.json()
        return [self._parse_offre(o) for o in data.get("resultats", [])]

    def _parse_offre(self, o: dict) -> dict:
        contrat_raw = o.get("typeContratLibelle") or o.get("typeContrat") or ""

        salaire = ""
        sal = o.get("salaire", {})
        if sal.get("libelle"):
            salaire = sal["libelle"]
            if sal.get("complement1"):
                salaire += f" + {sal['complement1']}"

        remote = ""
        if o.get("experienceLibelle"):
            pass
        teletravail = (o.get("qualitesProfessionnelles") or [])
        if any("télétravail" in str(q).lower() for q in teletravail):
            remote = "Télétravail partiel"

        lieu = o.get("lieuTravail", {})
        location = lieu.get("libelle", "")

        url = (o.get("origineOffre") or {}).get("urlOrigine") or \
              f"https://www.francetravail.fr/offres/recherche/detail/{o.get('id', '')}"

        return self.normalize({
            "external_id":   o.get("id", ""),
            "title":         o.get("intitule", ""),
            "company":       (o.get("entreprise") or {}).get("nom", ""),
            "contract_type": contrat_raw,
            "location":      location,
            "remote":        remote,
            "salary":        salaire,
            "url":           url,
            "description":   o.get("description", "")[:500],
            "pub_date":      (o.get("dateCreation") or "")[:10],
        })
