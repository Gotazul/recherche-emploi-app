#!/usr/bin/env python3
"""
Agent local Indeed — scrape Indeed sur ce PC et envoie les résultats au serveur distant.

Usage :
    python agent_indeed.py --server http://192.168.0.34:8001
    python agent_indeed.py --server http://192.168.0.34:8001 --profile <profile_id>
"""
import argparse
import logging
import sys
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Agent Indeed local")
    parser.add_argument("--server", default="http://192.168.0.34:8001", help="URL du serveur distant")
    parser.add_argument("--profile", default=None, help="ID du profil à scraper (tous si omis)")
    args = parser.parse_args()

    base = args.server.rstrip("/")

    # Récupère profils et sites depuis le serveur
    profiles = requests.get(f"{base}/api/profiles").json()
    sites    = requests.get(f"{base}/api/sites").json()

    indeed_site = next((s for s in sites if s["name"].lower() == "indeed" and s["active"]), None)
    if not indeed_site:
        logger.error("Site Indeed introuvable ou inactif sur le serveur.")
        sys.exit(1)

    if args.profile:
        profiles = [p for p in profiles if p["id"] == args.profile]
        if not profiles:
            logger.error("Profil %s introuvable.", args.profile)
            sys.exit(1)

    active_profiles = [p for p in profiles if p["active"]]
    if not active_profiles:
        logger.info("Aucun profil actif.")
        return

    # Import local du scraper Indeed
    from scrapers.indeed import IndeedScraper
    scraper = IndeedScraper(indeed_site)

    for profile in active_profiles:
        criteria = profile.get("criteria", {})
        logger.info("Scraping Indeed pour le profil « %s »...", profile["name"])
        try:
            listings = scraper.fetch_listings(criteria)
            logger.info("%d offre(s) trouvée(s)", len(listings))
        except Exception as e:
            logger.error("Erreur scraping : %s", e)
            continue

        if not listings:
            continue

        resp = requests.post(f"{base}/api/agent/import", json={
            "profile_id": profile["id"],
            "site_id":    indeed_site["id"],
            "listings":   listings,
        })

        if resp.ok:
            r = resp.json()
            logger.info("Envoyé au serveur : %d nouvelle(s), %d mise(s) à jour", r["new"], r["updated"])
        else:
            logger.error("Erreur serveur %s : %s", resp.status_code, resp.text)


if __name__ == "__main__":
    main()
