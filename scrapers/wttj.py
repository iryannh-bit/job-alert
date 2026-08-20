"""
Scraper Welcome to the Jungle — utilise l'API Algolia publique de WTTJ.
Les credentials Algolia sont extraits dynamiquement depuis la page WTTJ.
"""
import re
import hashlib
import logging
import requests
import time

logger = logging.getLogger("scraper.wttj")

WTTJ_BASE   = "https://www.welcometothejungle.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Credentials Algolia connus — mis à jour dynamiquement si besoin
_ALGOLIA_APP_ID  = "O6QCEW69WK"
_ALGOLIA_API_KEY = ""   # Extrait dynamiquement
_ALGOLIA_INDEX   = "wttj_jobs_production_fr"


def _get_algolia_credentials() -> tuple[str, str]:
    """Extrait les credentials Algolia depuis la page de recherche WTTJ."""
    global _ALGOLIA_API_KEY
    if _ALGOLIA_API_KEY:
        return _ALGOLIA_APP_ID, _ALGOLIA_API_KEY
    try:
        r = requests.get(f"{WTTJ_BASE}/fr/jobs", headers=HEADERS, timeout=20)
        app_id_match  = re.search(r'"applicationID"\s*:\s*"([^"]+)"', r.text)
        api_key_match = re.search(r'"apiKey"\s*:\s*"([a-f0-9]{32})"',  r.text)
        if app_id_match and api_key_match:
            app_id  = app_id_match.group(1)
            api_key = api_key_match.group(1)
            _ALGOLIA_API_KEY = api_key
            logger.debug(f"Algolia credentials extraits : app_id={app_id}")
            return app_id, api_key
    except Exception as e:
        logger.warning(f"Extraction Algolia échouée : {e}")
    # Fallback avec clé connue
    _ALGOLIA_API_KEY = "bc25df5e0a5bde1d1b3c9b53f3e7fffd"
    return _ALGOLIA_APP_ID, _ALGOLIA_API_KEY


def _algolia_search(query: str, filters: str = "", hits_per_page: int = 50) -> list[dict]:
    app_id, api_key = _get_algolia_credentials()
    url = (f"https://{app_id.lower()}-dsn.algolia.net/1/indexes/"
           f"{_ALGOLIA_INDEX}/query")
    headers = {
        "X-Algolia-Application-Id": app_id,
        "X-Algolia-API-Key":        api_key,
        "Content-Type":             "application/json",
    }
    payload = {
        "query":        query,
        "filters":      filters,
        "hitsPerPage":  hits_per_page,
        "attributesToRetrieve": [
            "name", "company_name", "offices", "contract_type",
            "published_at", "description", "slug", "company_slug",
        ],
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return r.json().get("hits", [])
    except Exception as e:
        logger.error(f"Algolia query échouée pour '{query}' : {e}")
        return []


def _hit_to_job(hit: dict, source_label: str) -> dict:
    offices  = hit.get("offices", [{}])
    location = offices[0].get("city", "") if offices else ""
    country  = offices[0].get("country_code", "") if offices else ""
    loc_str  = f"{location}, {country}".strip(", ")

    slug         = hit.get("slug", "")
    company_slug = hit.get("company_slug", "")
    url = f"{WTTJ_BASE}/fr/companies/{company_slug}/jobs/{slug}" if slug else WTTJ_BASE

    raw_id  = f"wttj_{hit.get('objectID', slug)}"
    job_id  = hashlib.md5(raw_id.encode()).hexdigest()[:16]

    return {
        "id":            job_id,
        "title":         hit.get("name", ""),
        "company":       hit.get("company_name", ""),
        "location":      loc_str,
        "contract_type": hit.get("contract_type", ""),
        "description":   hit.get("description", "")[:1000],
        "url":           url,
        "source":        source_label,
        "date_range":    "",
    }


class WTTJScraper:
    name = "WTTJ"

    def search_recherche(self, recherche_config: list[dict]) -> list[dict]:
        """Cherche les offres pour tous les types de postes de 'Recherche entreprise'."""
        results = []
        for entry in recherche_config:
            if "welcometothejungle" not in " ".join(entry.get("sites", [])).lower():
                continue
            query = entry["job_type"]
            logger.debug(f"WTTJ Recherche : '{query}'")
            hits = _algolia_search(
                query=query,
                filters='contract_type:"internship"',
            )
            for hit in hits:
                job = _hit_to_job(hit, "WTTJ")
                job["date_range"] = entry.get("date_range", "")
                results.append(job)
            time.sleep(0.5)
        return results

    def search_pour_plus_tard(self, ppt_config: list[dict]) -> list[dict]:
        """Cherche les offres pour les entreprises ciblées de 'Pour plus tard'."""
        results = []
        for entry in ppt_config:
            company = entry["company"]
            position = entry["position"]
            query = f"{position} {company}"
            logger.debug(f"WTTJ PPT : '{query}'")
            hits = _algolia_search(
                query=query,
                filters='contract_type:"internship"',
                hits_per_page=20,
            )
            for hit in hits:
                # Ne garder que si le nom de l'entreprise correspond
                if company.lower() not in hit.get("company_name", "").lower():
                    continue
                job = _hit_to_job(hit, "WTTJ")
                job["date_range"] = entry.get("date_range", "")
                results.append(job)
            time.sleep(0.5)
        return results
