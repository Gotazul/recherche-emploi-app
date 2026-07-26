import re
import unicodedata


def _ascii_lower(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _ascii_lower(text)))


def matches_criteria(listing: dict, criteria: dict) -> bool:
    """Post-scraping filter : mots-clés, contrat, télétravail."""

    # Mots-clés : au moins un doit apparaître dans le titre ou la description
    keywords = [_ascii_lower(k) for k in criteria.get("keywords", []) if k.strip()]
    if keywords:
        haystack = _tokens(
            (listing.get("title") or "") + " " + (listing.get("description") or "")
        )
        if not any(any(tok.startswith(kw) for tok in haystack) for kw in keywords):
            return False

    # Type de contrat
    allowed_contracts = [c.lower() for c in criteria.get("contract_types", [])]
    if allowed_contracts:
        listing_contract = (listing.get("contract_type") or "").lower()
        if listing_contract and not any(c in listing_contract for c in allowed_contracts):
            return False

    # Télétravail
    remote_pref = criteria.get("remote")
    if remote_pref and remote_pref != "indifferent":
        listing_remote = (listing.get("remote") or "").lower()
        if remote_pref == "full" and "complet" not in listing_remote and "100" not in listing_remote:
            return False
        if remote_pref == "partial" and "partiel" not in listing_remote:
            return False

    return True
