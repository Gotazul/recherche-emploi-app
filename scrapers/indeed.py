import json
import logging
import re
import requests
from urllib.parse import urlencode, quote_plus
from bs4 import BeautifulSoup
from .base import BaseScraper, HEADERS

logger = logging.getLogger(__name__)

_BASE = "https://fr.indeed.com/emplois"

# Indeed utilise des miles pour le rayon, on convertit
_KM_TO_MILES = 0.621371
_RADIUS_MILES = {25: 15, 50: 25, 100: 50, 150: 100}

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
        return _BASE + "?" + urlencode(self._build_params(criteria))

    def _build_params(self, criteria: dict) -> dict:
        params = {}

        keywords = criteria.get("keywords", [])
        if keywords:
            params["q"] = " ".join(keywords)

        location = (criteria.get("location") or "").strip()
        if location:
            params["l"] = location

        radius_km = criteria.get("radius_km")
        if radius_km:
            # Trouver le palier le plus proche en miles
            miles = min(_RADIUS_MILES.items(), key=lambda x: abs(x[0] - radius_km))[1]
            params["radius"] = miles

        contracts = criteria.get("contract_types", [])
        codes = list(dict.fromkeys(
            _CONTRACT_CODE[c.lower()] for c in contracts if c.lower() in _CONTRACT_CODE
        ))
        if len(codes) == 1:
            params["jt"] = codes[0]

        params["lang"] = "fr"
        return params

    def fetch_listings(self, criteria: dict) -> list[dict]:
        url = self.build_url(criteria)
        session = requests.Session()
        hdrs = {
            **HEADERS,
            "Referer": "https://fr.indeed.com/",
            "Accept-Language": "fr-FR,fr;q=0.9",
        }
        # Premier appel pour récupérer les cookies
        session.get("https://fr.indeed.com/", headers=hdrs, timeout=10)
        resp = session.get(url, headers=hdrs, timeout=15)

        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code} — Indeed a refusé la requête")

        listings = self._extract_json(resp.text)
        if not listings:
            listings = self._parse_html(resp.text)
        if not listings:
            raise Exception("Aucune offre trouvée (protection anti-bot probable)")

        return listings

    def _extract_json(self, html: str) -> list[dict]:
        """Indeed embarque les offres dans window.mosaic.providerData."""
        m = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});',
            html, re.DOTALL
        )
        if not m:
            return []
        try:
            data = json.loads(m.group(1))
            jobs = (
                data.get("metaData", {})
                    .get("mosaicProviderJobCardsModel", {})
                    .get("results", [])
            )
            return [self._parse_json_job(j) for j in jobs if j.get("jobkey")]
        except Exception as e:
            logger.warning("Parsing JSON Indeed échoué : %s", e)
            return []

    def _parse_json_job(self, j: dict) -> dict:
        salary = ""
        sal = j.get("extractedSalary") or {}
        if sal.get("min") and sal.get("max"):
            unit = "€/an" if sal.get("type") == "yearly" else "€/mois"
            salary = f"{int(sal['min']):,} – {int(sal['max']):,} {unit}".replace(",", " ")
        elif j.get("salarySnippet", {}).get("text"):
            salary = j["salarySnippet"]["text"]

        remote = ""
        tags = [t.get("label", "") for t in (j.get("taxonomyAttributes") or [])]
        for tag in tags:
            tl = tag.lower()
            if "100%" in tl and "télétravail" in tl:
                remote = "100% télétravail"
                break
            if "télétravail" in tl or "remote" in tl:
                remote = "Télétravail partiel"

        ext_id = j.get("jobkey", "")
        url = f"https://fr.indeed.com/voir-emploi?jk={ext_id}" if ext_id else ""

        return self.normalize({
            "external_id":   ext_id,
            "title":         j.get("normTitle") or j.get("title", ""),
            "company":       j.get("company", ""),
            "contract_type": j.get("jobType") or "",
            "location":      j.get("formattedLocation", ""),
            "remote":        remote,
            "salary":        salary,
            "url":           url,
            "description":   j.get("snippet", ""),
            "pub_date":      "",
        })

    def _parse_html(self, html: str) -> list[dict]:
        """Fallback : parsing HTML des cartes d'offres."""
        soup = BeautifulSoup(html, "lxml")
        cards = soup.find_all("div", attrs={"data-testid": "slider_item"})
        if not cards:
            cards = soup.find_all("li", class_=re.compile(r"css-.*eu4oa1w0", re.I))
        results = []
        for card in cards:
            try:
                results.append(self._parse_html_card(card))
            except Exception:
                continue
        return results

    def _parse_html_card(self, card) -> dict:
        title_el = card.find("h2", class_=re.compile(r"jobTitle", re.I))
        title = title_el.get_text(strip=True) if title_el else ""

        company_el = card.find(attrs={"data-testid": "company-name"})
        company = company_el.get_text(strip=True) if company_el else ""

        loc_el = card.find(attrs={"data-testid": "text-location"})
        location = loc_el.get_text(strip=True) if loc_el else ""

        salary_el = card.find(class_=re.compile(r"salary", re.I))
        salary = salary_el.get_text(strip=True) if salary_el else ""

        link = card.find("a", href=re.compile(r"/voir-emploi|/rc/clk"))
        href = link.get("href", "") if link else ""
        if href and not href.startswith("http"):
            href = "https://fr.indeed.com" + href

        ext_id_m = re.search(r"jk=([a-z0-9]+)", href)
        ext_id = ext_id_m.group(1) if ext_id_m else href

        return self.normalize({
            "external_id": ext_id,
            "title":       title,
            "company":     company,
            "location":    location,
            "salary":      salary,
            "url":         href,
        })
