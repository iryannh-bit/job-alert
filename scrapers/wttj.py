"""
Scraper Welcome to the Jungle — extrait les offres depuis le __NEXT_DATA__
embarqué dans la page de recherche HTML (contourne l'API Algolia bloquée).
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

def _wttj_search(query: str, contract_type: str = "internship", hits_per_page: int = 50) -> list[dict]:
    """Cherche des offres WTTJ via la page de recherche (contourne Algolia)."""
    import json as _json
    params = {
        "query": query,
        "contract_type[]": contract_type,
        "page": 1,
    }
    try:
        r = requests.get(f"{WTTJ_BASE}/fr/jobs", params=params, headers=HEADERS, timeout=25)
        r.raise_for_status()
        # WTTJ utilise Next.js — les données sont dans __NEXT_DATA__
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', r.text, re.DOTALL)
        if not match:
            logger.warning("WTTJ : __NEXT_DATA__ introuvable dans la page")
            return []
        data = _json.loads(match.group(1))
        # Chemin dans le JSON Next.js
        jobs_raw = (
            data.get("props", {})
                .get("pageProps", {})
                .get("jobs", [])
        )
        if not jobs_raw:
            # Essayer un autre chemin possible
            jobs_raw = (
                data.get("props", {})
                    .get("pageProps", {})
                    .get("data", {})
                    .get("jobs", {})
                    .get("data", [])
            )
        logger.info(f"WTTJ : {len(jobs_raw)} offres trouvées pour '{query}'")
        return jobs_raw[:hits_per_page]
    except Exception as e:
        logger.error(f"WTTJ query échouée pour '{query}' : {e}")
        return []


def _hit_to_job(hit: dict, source_label: str) -> dict:
    # Support deux structures : Algolia (company_name) et Next.js (organization.name)
    org      = hit.get("organization", {}) or {}
    company  = hit.get("company_name", "") or org.get("name", "")

    offices  = hit.get("offices", [{}]) or [{}]
    if isinstance(offices, list) and offices:
        loc_city    = offices[0].get("city", "") or offices[0].get("name", "")
        loc_country = offices[0].get("country_code", "")
    else:
        loc_city, loc_country = "", ""
    loc_str = f"{loc_city}, {loc_country}".strip(", ")

    slug         = hit.get("slug", "")
    company_slug = hit.get("company_slug", "") or org.get("slug", "")
    url = f"{WTTJ_BASE}/fr/companies/{company_slug}/jobs/{slug}" if slug else WTTJ_BASE

    raw_id = f"wttj_{hit.get('objectID', hit.get('id', slug))}"
    job_id = hashlib.md5(raw_id.encode()).hexdigest()[:16]

    return {
        "id":            job_id,
        "title":         hit.get("name", hit.get("title", "")),
        "company":       company,
        "location":      loc_str,
        "contract_type": hit.get("contract_type", "internship"),
        "description":   (hit.get("description", "") or "")[:1000],
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
            hits = _wttj_search(query=query, contract_type="internship")
            for hit in hits:
                job = _hit_to_job(hit, "WTTJ")
                job["date_range"] = entry.get("date_range", "")
                results.append(job)
            time.sleep(1.0)
        return results

    def search_pour_plus_tard(self, ppt_config: list[dict]) -> list[dict]:
        """Cherche les offres pour les entreprises ciblées de 'Pour plus tard'."""
        results = []
        for entry in ppt_config:
            company  = entry["company"]
            position = entry["position"]
            query    = f"{position} {company}"
            logger.debug(f"WTTJ PPT : '{query}'")
            hits = _wttj_search(query=query, contract_type="internship", hits_per_page=20)
            for hit in hits:
                org         = hit.get("organization", {}) or {}
                company_name = hit.get("company_name", "") or org.get("name", "")
                if company.lower() not in company_name.lower():
                    continue
                job = _hit_to_job(hit, "WTTJ")
                job["date_range"] = entry.get("date_range", "")
                results.append(job)
            time.sleep(1.0)
        return results
