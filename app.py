import csv
import io
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database as db
from filters import matches_criteria
from scrapers import get_scraper


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    yield


app = FastAPI(title="Recherche Emploi", version="1.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


# ── Profiles ──────────────────────────────────────────────────────────────────

class ProfileIn(BaseModel):
    name: str
    criteria: dict = {}
    active: Optional[bool] = None


@app.get("/api/profiles")
def get_profiles():
    return db.list_profiles()


@app.post("/api/profiles", status_code=201)
def create_profile(body: ProfileIn):
    return db.create_profile(body.name, body.criteria)


@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: str):
    p = db.get_profile(profile_id)
    if not p:
        raise HTTPException(404, "Profil introuvable")
    return p


@app.put("/api/profiles/{profile_id}")
def update_profile(profile_id: str, body: ProfileIn):
    p = db.update_profile(profile_id, body.name, body.criteria, body.active)
    if not p:
        raise HTTPException(404, "Profil introuvable")
    return p


@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str):
    if not db.delete_profile(profile_id):
        raise HTTPException(404, "Profil introuvable")
    return {"ok": True}


# ── Sites ─────────────────────────────────────────────────────────────────────

class SiteIn(BaseModel):
    name: Optional[str] = None
    url_base: Optional[str] = None
    access_mode: Optional[str] = None
    active: Optional[bool] = None


@app.get("/api/sites")
def get_sites():
    return db.list_sites()


@app.post("/api/sites", status_code=201)
def create_site(body: SiteIn):
    if not body.name or not body.url_base:
        raise HTTPException(400, "name et url_base sont requis")
    return db.create_site(body.name, body.url_base, body.access_mode or "direct")


@app.get("/api/sites/{site_id}")
def get_site(site_id: str):
    s = db.get_site(site_id)
    if not s:
        raise HTTPException(404, "Site introuvable")
    return s


@app.put("/api/sites/{site_id}")
def update_site(site_id: str, body: SiteIn):
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.url_base is not None:
        updates["url_base"] = body.url_base
    if body.access_mode is not None:
        updates["access_mode"] = body.access_mode
    if body.active is not None:
        updates["active"] = int(body.active)
    s = db.update_site(site_id, **updates)
    if not s:
        raise HTTPException(404, "Site introuvable")
    return s


@app.delete("/api/sites/{site_id}")
def delete_site(site_id: str):
    if not db.delete_site(site_id):
        raise HTTPException(404, "Site introuvable")
    return {"ok": True}


# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/api/search/{profile_id}")
def run_search(profile_id: str, site_ids: list[str] = Query(default=[])):
    profile = db.get_profile(profile_id)
    if not profile:
        raise HTTPException(404, "Profil introuvable")

    criteria = profile["criteria"]
    sites = db.list_sites()
    active_sites = [s for s in sites if s["active"] and (not site_ids or s["id"] in site_ids)]

    results = []
    total_new = 0
    total_updated = 0

    for site in active_sites:
        scraper = get_scraper(site)
        if not scraper or site["access_mode"] != "direct":
            results.append({
                "site_id": site["id"],
                "site_name": site["name"],
                "search_url": site["url_base"],
                "listings_found": 0,
                "new": 0,
                "updated": 0,
                "error": "Mode manuel — scraping non disponible pour ce site",
            })
            continue

        result = scraper.search(criteria)
        site_new = 0
        site_updated = 0
        seen_ids = []

        raw_count = len(result["listings"])
        filtered = [l for l in result["listings"] if matches_criteria(l, criteria)]

        for listing_data in filtered:
            listing_data["profile_id"] = profile_id
            if not listing_data.get("external_id"):
                continue
            _, is_new = db.upsert_listing(listing_data)
            seen_ids.append(listing_data["external_id"])
            if is_new:
                site_new += 1
            else:
                site_updated += 1

        if seen_ids:
            # Vérifie les annonces absentes de ce scrape via leur URL avant de les marquer gone
            unseen = db.get_active_listings_not_in(profile_id, site["id"], seen_ids)
            confirmed_gone = []
            for row in unseen:
                alive = scraper.verify_alive(row["url"])
                if alive is False:
                    confirmed_gone.append(row["external_id"])
                # alive=True ou None → on laisse la logique des 7 jours décider
            if confirmed_gone:
                db.mark_gone_by_ids(profile_id, site["id"], confirmed_gone)
            db.mark_gone_if_not_seen(profile_id, site["id"], seen_ids)

        total_new += site_new
        total_updated += site_updated
        results.append({
            "site_id": site["id"],
            "site_name": site["name"],
            "search_url": result["search_url"],
            "listings_found": len(filtered),
            "listings_raw": raw_count,
            "filtered_out": raw_count - len(filtered),
            "new": site_new,
            "updated": site_updated,
            "error": result.get("error"),
        })

    return {
        "profile_id": profile_id,
        "profile_name": profile["name"],
        "total_new": total_new,
        "total_updated": total_updated,
        "sites": results,
    }


# ── Listings ──────────────────────────────────────────────────────────────────

class ListingUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


@app.delete("/api/listings")
def clear_listings(profile_id: Optional[str] = None):
    with db.get_db() as conn:
        if profile_id:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM listings WHERE profile_id=?", (profile_id,)
            ).fetchall()]
            if ids:
                ph = ",".join("?" * len(ids))
                conn.execute(f"DELETE FROM listings WHERE id IN ({ph})", ids)
            count = len(ids)
        else:
            count = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
            conn.execute("DELETE FROM listings")
    return {"deleted": count}


@app.get("/api/listings")
def get_listings(
    profile_id: Optional[str] = None,
    site_id: Optional[str] = None,
    status: Optional[str] = None,
    contract_type: Optional[str] = None,
    location: Optional[str] = None,
    remote: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    listings, total = db.list_listings(
        profile_id=profile_id, site_id=site_id, status=status,
        contract_type=contract_type, location=location, remote=remote,
        limit=limit, offset=offset,
    )
    return {"items": listings, "total": total}


@app.get("/api/listings/compare")
def compare_listings(ids: str = Query(...)):
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    return db.get_listings_by_ids(id_list)


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: str):
    l = db.get_listing(listing_id)
    if not l:
        raise HTTPException(404, "Annonce introuvable")
    return l


@app.put("/api/listings/{listing_id}")
def update_listing(listing_id: str, body: ListingUpdate):
    l = db.update_listing(listing_id, body.status, body.notes)
    if not l:
        raise HTTPException(404, "Annonce introuvable")
    return l


@app.delete("/api/listings/{listing_id}")
def delete_listing(listing_id: str):
    if not db.delete_listing(listing_id):
        raise HTTPException(404, "Annonce introuvable")
    return {"ok": True}


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard():
    return db.get_dashboard_stats()


# ── Export CSV ────────────────────────────────────────────────────────────────

@app.get("/api/export/{profile_id}")
def export_csv(profile_id: str):
    listings, _ = db.list_listings(profile_id=profile_id, limit=10000)

    def generate():
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "id", "titre", "entreprise", "contrat", "localisation", "teletravail",
            "salaire", "statut", "site", "url", "premiere_detection", "notes"
        ])
        writer.writeheader()
        yield output.getvalue()
        output.seek(0); output.truncate(0)

        for l in listings:
            writer.writerow({
                "id": l["id"],
                "titre": l["title"],
                "entreprise": l["company"],
                "contrat": l["contract_type"],
                "localisation": l["location"],
                "teletravail": l["remote"],
                "salaire": l["salary"],
                "statut": l["status"],
                "site": l["site_name"],
                "url": l["url"],
                "premiere_detection": l["first_detected"],
                "notes": l["notes"],
            })
            yield output.getvalue()
            output.seek(0); output.truncate(0)

    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=offres_{profile_id[:8]}.csv"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8001, reload=True)
