import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "emploi.db"

DEFAULT_SITES = [
    {"name": "Indeed",              "url_base": "https://fr.indeed.com",                    "access_mode": "direct"},
    {"name": "APEC",                "url_base": "https://www.apec.fr",                      "access_mode": "direct"},
    {"name": "France Travail",      "url_base": "https://www.francetravail.fr",             "access_mode": "direct"},
    {"name": "LinkedIn",            "url_base": "https://www.linkedin.com",                 "access_mode": "direct"},
    {"name": "Welcome to the Jungle", "url_base": "https://www.welcometothejungle.com",     "access_mode": "direct"},
]

_ALLOWED_SITE_FIELDS = frozenset({"name", "url_base", "access_mode", "active"})


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS search_profiles (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                criteria    TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                active      INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS sites (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                url_base    TEXT NOT NULL,
                access_mode TEXT NOT NULL DEFAULT 'direct',
                active      INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS listings (
                id              TEXT PRIMARY KEY,
                external_id     TEXT,
                site_id         TEXT NOT NULL,
                profile_id      TEXT NOT NULL,
                title           TEXT,
                company         TEXT,
                contract_type   TEXT,
                location        TEXT,
                remote          TEXT,
                salary          TEXT,
                url             TEXT,
                description     TEXT,
                pub_date        TEXT,
                first_detected  TEXT NOT NULL,
                last_detected   TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'new',
                notes           TEXT DEFAULT '',
                FOREIGN KEY (site_id) REFERENCES sites(id),
                FOREIGN KEY (profile_id) REFERENCES search_profiles(id),
                UNIQUE(external_id, site_id, profile_id)
            );

            CREATE INDEX IF NOT EXISTS idx_listings_profile ON listings(profile_id);
            CREATE INDEX IF NOT EXISTS idx_listings_site    ON listings(site_id);
            CREATE INDEX IF NOT EXISTS idx_listings_status  ON listings(status);
        """)

        count = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        if count == 0:
            now = datetime.utcnow().isoformat()
            for site in DEFAULT_SITES:
                conn.execute(
                    "INSERT INTO sites (id, name, url_base, access_mode, active, created_at) VALUES (?,?,?,?,1,?)",
                    (str(uuid.uuid4()), site["name"], site["url_base"], site["access_mode"], now)
                )


# ── Profiles ──────────────────────────────────────────────────────────────────

def _parse_profile(row: dict) -> dict:
    if isinstance(row.get("criteria"), str):
        row["criteria"] = json.loads(row["criteria"])
    return row


def list_profiles() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM search_profiles ORDER BY created_at DESC").fetchall()
        return [_parse_profile(dict(r)) for r in rows]


def get_profile(profile_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM search_profiles WHERE id=?", (profile_id,)).fetchone()
        return _parse_profile(dict(row)) if row else None


def create_profile(name: str, criteria: dict) -> dict:
    now = datetime.utcnow().isoformat()
    pid = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO search_profiles (id, name, criteria, created_at, updated_at) VALUES (?,?,?,?,?)",
            (pid, name, json.dumps(criteria), now, now)
        )
    return get_profile(pid)


def update_profile(profile_id: str, name: str | None, criteria: dict | None, active: bool | None) -> dict | None:
    profile = get_profile(profile_id)
    if not profile:
        return None
    now = datetime.utcnow().isoformat()
    new_name     = name if name is not None else profile["name"]
    new_criteria = json.dumps(criteria) if criteria is not None else json.dumps(profile["criteria"])
    new_active   = int(active) if active is not None else profile["active"]
    with get_db() as conn:
        conn.execute(
            "UPDATE search_profiles SET name=?, criteria=?, active=?, updated_at=? WHERE id=?",
            (new_name, new_criteria, new_active, now, profile_id)
        )
    return get_profile(profile_id)


def delete_profile(profile_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM search_profiles WHERE id=?", (profile_id,))
        return cur.rowcount > 0


# ── Sites ─────────────────────────────────────────────────────────────────────

def list_sites() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM sites ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def get_site(site_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM sites WHERE id=?", (site_id,)).fetchone()
        return dict(row) if row else None


def create_site(name: str, url_base: str, access_mode: str) -> dict:
    now = datetime.utcnow().isoformat()
    sid = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sites (id, name, url_base, access_mode, active, created_at) VALUES (?,?,?,?,1,?)",
            (sid, name, url_base, access_mode, now)
        )
    return get_site(sid)


def update_site(site_id: str, **kwargs) -> dict | None:
    if not get_site(site_id):
        return None
    fields = {k: v for k, v in kwargs.items() if k in _ALLOWED_SITE_FIELDS and v is not None}
    if not fields:
        return get_site(site_id)
    sets = ", ".join(f"{k}=?" for k in fields)
    with get_db() as conn:
        conn.execute(f"UPDATE sites SET {sets} WHERE id=?", (*fields.values(), site_id))
    return get_site(site_id)


def delete_site(site_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM sites WHERE id=?", (site_id,))
        return cur.rowcount > 0


# ── Listings ──────────────────────────────────────────────────────────────────

def upsert_listing(data: dict) -> tuple[dict, bool]:
    """Insert or update a listing. Returns (listing, is_new)."""
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT * FROM listings WHERE external_id=? AND site_id=? AND profile_id=?",
            (data["external_id"], data["site_id"], data["profile_id"])
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE listings SET title=?, company=?, contract_type=?, location=?,
                   remote=?, salary=?, url=?, description=?, pub_date=?, last_detected=?
                   WHERE id=?""",
                (data.get("title"), data.get("company"), data.get("contract_type"),
                 data.get("location"), data.get("remote"), data.get("salary"),
                 data.get("url"), data.get("description"), data.get("pub_date"),
                 now, existing["id"])
            )
            row = conn.execute("SELECT * FROM listings WHERE id=?", (existing["id"],)).fetchone()
            return dict(row), False

        # Soft-dedup : même titre + entreprise + localisation → même offre republiée
        if data.get("title") and data.get("company"):
            duplicate = conn.execute(
                """SELECT * FROM listings
                   WHERE title=? AND company=? AND location=? AND site_id=? AND profile_id=?""",
                (data["title"], data["company"], data.get("location", ""),
                 data["site_id"], data["profile_id"])
            ).fetchone()
            if duplicate:
                conn.execute(
                    "UPDATE listings SET last_detected=?, external_id=? WHERE id=?",
                    (now, data["external_id"], duplicate["id"])
                )
                return dict(duplicate), False

        lid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO listings
               (id, external_id, site_id, profile_id, title, company, contract_type,
                location, remote, salary, url, description, pub_date,
                first_detected, last_detected, status, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new','')""",
            (lid, data.get("external_id"), data["site_id"], data["profile_id"],
             data.get("title"), data.get("company"), data.get("contract_type"),
             data.get("location"), data.get("remote"), data.get("salary"),
             data.get("url"), data.get("description"), data.get("pub_date"),
             now, now)
        )
        row = conn.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
        return dict(row), True


def list_listings(profile_id=None, site_id=None, status=None,
                  contract_type=None, location=None, remote=None,
                  limit=200, offset=0):
    conditions = []
    params = []
    if profile_id:
        conditions.append("l.profile_id=?"); params.append(profile_id)
    if site_id:
        conditions.append("l.site_id=?"); params.append(site_id)
    if status:
        statuses = status.split(",")
        placeholders = ",".join("?" * len(statuses))
        conditions.append(f"l.status IN ({placeholders})"); params.extend(statuses)
    if contract_type:
        conditions.append("l.contract_type=?"); params.append(contract_type)
    if location:
        conditions.append("l.location LIKE ?"); params.append(f"%{location}%")
    if remote:
        conditions.append("l.remote=?"); params.append(remote)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT l.*, s.name as site_name, p.name as profile_name
            FROM listings l
            JOIN sites s ON s.id = l.site_id
            JOIN search_profiles p ON p.id = l.profile_id
            {where}
            ORDER BY l.first_detected DESC
            LIMIT ? OFFSET ?
        """, params).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) FROM listings l {where}", params[:-2]
        ).fetchone()[0]
        return [dict(r) for r in rows], total


def get_listing(listing_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("""
            SELECT l.*, s.name as site_name, p.name as profile_name
            FROM listings l
            JOIN sites s ON s.id = l.site_id
            JOIN search_profiles p ON p.id = l.profile_id
            WHERE l.id=?
        """, (listing_id,)).fetchone()
        return dict(row) if row else None


def update_listing(listing_id: str, status: str | None, notes: str | None) -> dict | None:
    if not get_listing(listing_id):
        return None
    updates = {}
    if status is not None:
        updates["status"] = status
    if notes is not None:
        updates["notes"] = notes
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        with get_db() as conn:
            conn.execute(f"UPDATE listings SET {sets} WHERE id=?", (*updates.values(), listing_id))
    return get_listing(listing_id)


def delete_listing(listing_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM listings WHERE id=?", (listing_id,))
        return cur.rowcount > 0


def get_listings_by_ids(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT l.*, s.name as site_name, p.name as profile_name
            FROM listings l
            JOIN sites s ON s.id = l.site_id
            JOIN search_profiles p ON p.id = l.profile_id
            WHERE l.id IN ({placeholders})
        """, ids).fetchall()
        return [dict(r) for r in rows]


def get_active_listings_not_in(profile_id: str, site_id: str, seen_external_ids: list[str]) -> list[dict]:
    """Retourne les annonces actives (non gone/dismissed) absentes du dernier scrape."""
    with get_db() as conn:
        if not seen_external_ids:
            return []
        placeholders = ",".join("?" * len(seen_external_ids))
        rows = conn.execute(f"""
            SELECT external_id, url FROM listings
            WHERE profile_id=? AND site_id=? AND url != ''
            AND status NOT IN ('gone','dismissed','interesting','applied')
            AND external_id NOT IN ({placeholders})
        """, [profile_id, site_id] + seen_external_ids).fetchall()
        return [dict(r) for r in rows]


def mark_gone_by_ids(profile_id: str, site_id: str, external_ids: list[str]):
    """Marque 'gone' une liste précise d'annonces (vérifiées mortes via URL)."""
    if not external_ids:
        return
    with get_db() as conn:
        placeholders = ",".join("?" * len(external_ids))
        conn.execute(f"""
            UPDATE listings SET status='gone'
            WHERE profile_id=? AND site_id=?
            AND status NOT IN ('dismissed','interesting','applied')
            AND external_id IN ({placeholders})
        """, [profile_id, site_id] + external_ids)


def mark_gone_if_not_seen(profile_id: str, site_id: str, seen_external_ids: list[str], days_threshold: int = 7):
    """Marque 'gone' uniquement les annonces absentes depuis plus de days_threshold jours."""
    cutoff = (datetime.utcnow() - timedelta(days=days_threshold)).isoformat()
    with get_db() as conn:
        if seen_external_ids:
            placeholders = ",".join("?" * len(seen_external_ids))
            conn.execute(f"""
                UPDATE listings SET status='gone'
                WHERE profile_id=? AND site_id=? AND status NOT IN ('dismissed','interesting','applied')
                AND last_detected < ? AND external_id NOT IN ({placeholders})
            """, [profile_id, site_id, cutoff] + seen_external_ids)
        else:
            conn.execute("""
                UPDATE listings SET status='gone'
                WHERE profile_id=? AND site_id=? AND status NOT IN ('dismissed','interesting','applied')
                AND last_detected < ?
            """, [profile_id, site_id, cutoff])


# ── Dashboard ─────────────────────────────────────────────────────────────────

def get_dashboard_stats() -> dict:
    with get_db() as conn:
        by_status = conn.execute(
            "SELECT status, COUNT(*) as count FROM listings GROUP BY status"
        ).fetchall()
        by_site = conn.execute("""
            SELECT s.name, COUNT(*) as count
            FROM listings l JOIN sites s ON s.id=l.site_id
            GROUP BY s.name
        """).fetchall()
        recent = conn.execute("""
            SELECT l.*, s.name as site_name, p.name as profile_name
            FROM listings l
            JOIN sites s ON s.id=l.site_id
            JOIN search_profiles p ON p.id=l.profile_id
            WHERE l.status='new'
            ORDER BY l.first_detected DESC LIMIT 10
        """).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        return {
            "total": total,
            "by_status": {r["status"]: r["count"] for r in by_status},
            "by_site":   {r["name"]: r["count"] for r in by_site},
            "recent_new": [dict(r) for r in recent],
        }
