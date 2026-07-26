from abc import ABC, abstractmethod

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

CONTRACT_NORMALIZE = {
    "cdi": "CDI", "cdd": "CDD", "interim": "Intérim", "intérim": "Intérim",
    "alternance": "Alternance", "stage": "Stage",
    "freelance": "Freelance", "prestataire": "Freelance",
    "indépendant": "Freelance", "independant": "Freelance",
}


class BaseScraper(ABC):
    site_name: str = ""

    def __init__(self, site: dict):
        self.site = site
        self.site_id = site["id"]

    @abstractmethod
    def build_url(self, criteria: dict) -> str:
        pass

    @abstractmethod
    def fetch_listings(self, criteria: dict) -> list[dict]:
        pass

    def normalize(self, raw: dict) -> dict:
        contract_raw = (raw.get("contract_type") or "").lower().strip()
        contract = CONTRACT_NORMALIZE.get(contract_raw, raw.get("contract_type", ""))
        return {
            "external_id":   raw.get("external_id", ""),
            "site_id":       self.site_id,
            "title":         raw.get("title", ""),
            "company":       raw.get("company", ""),
            "contract_type": contract,
            "location":      raw.get("location", ""),
            "remote":        raw.get("remote", ""),
            "salary":        raw.get("salary", ""),
            "url":           raw.get("url", ""),
            "description":   raw.get("description", ""),
            "pub_date":      raw.get("pub_date", ""),
        }

    def search(self, criteria: dict) -> dict:
        url = self.build_url(criteria)
        try:
            listings = self.fetch_listings(criteria)
            error = None
        except Exception as e:
            listings = []
            error = str(e)
        return {
            "site_id":   self.site_id,
            "site_name": self.site["name"],
            "search_url": url,
            "listings":  listings,
            "error":     error,
        }
