from urllib.parse import urlencode
from .base import BaseScraper

# Indeed bloque systématiquement les requêtes automatiques (403 sur HTML et RSS).
# Ce scraper génère l'URL correcte pour un accès manuel.

_KM_TO_MILES = {25: 15, 50: 25, 75: 50, 100: 50, 150: 100}

_CONTRACT_CODE = {
    "cdi":        "fulltime",
    "cdd":        "contract",
    "intérim":    "temporary",
    "interim":    "temporary",
    "stage":      "internship",
    "alternance": "internship",
}


class IndeedScraper(BaseScraper):
    site_name = "Indeed"

    def build_url(self, criteria: dict) -> str:
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

        return "https://fr.indeed.com/emplois?" + urlencode(params)

    def fetch_listings(self, criteria: dict) -> list[dict]:
        raise Exception(
            "Indeed bloque les requêtes automatiques. "
            "Clique sur 'Ouvrir' pour consulter les offres manuellement."
        )
