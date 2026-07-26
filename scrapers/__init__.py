from .francetravail import FranceTravailScraper
from .indeed import IndeedScraper
from .apec import ApecScraper

SCRAPERS_BY_NAME = {
    "france travail": FranceTravailScraper,
    "indeed":         IndeedScraper,
    "apec":           ApecScraper,
}


def get_scraper(site: dict):
    key = site["name"].lower()
    cls = SCRAPERS_BY_NAME.get(key)
    if cls:
        return cls(site)
    return None
