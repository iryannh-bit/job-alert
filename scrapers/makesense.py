"""
Scraper Jobs that Make Sense — jobs.makesense.org
"""
import hashlib
import logging
import time
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("scraper.makesense")

BASE_URL = "https://jobs.makesense.org"
SEARCH_URL = f"{BASE_URL}/fr/jobs"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "application/json, text/html",
}


def _fetch_jobs(query: str, contract_type: str = "internship") -> list[dict]:
    params = {
        "query": query,
        "contractTypes[]": contract_type,
        "standalone": "true",
    }
    try:
        r = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=25)
        r.raise_for_status()
        return _parse(r.text, query)
    except Exception as e:
        logger.error(f"Make Sense erreur : {e}")
        return []


def _parse(html: str, query: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    selectors = [
        "article", ".job-card", "[class*='JobCard']", "[class*='job-item']",
        ".offer", "[class*='offer']", "li[class*='job']",
    ]
    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if len(cards) > 2:
            break

    # Fallback : liens offres
    if not cards:
        links = soup.select("a[href*='/fr/jobs/'], a[href*='/fr/offres/']")
        for link in links:
            title = link.get_text(strip=True)
            if len(title) < 10:
                continue
            href = link.get("href", "")
            url = BASE_URL + href if href.startswith("/") else href
            job_id = hashlib.md5(url.encode()).hexdigest()[:16]
            jobs.append({
                "id":            job_id,
                "title":         title,
                "company":       "",
                "location":      "",
                "contract_type": "Stage",
                "description":   "",
                "url":           url,
                "source":        "Make Sense",
                "date_range":    "",
            })
        return jobs

    for card in cards:
        try:
            title_el   = card.select_one("h2, h3, h4, .title, [class*='title'], [class*='name']")
            company_el = card.select_one("[class*='company'], [class*='organization'], [class*='employer']")
            loc_el     = card.select_one("[class*='location'], [class*='city'], [class*='place']")
            link_el    = card.select_one("a[href]")
            desc_el    = card.select_one("p, [class*='desc'], [class*='summary']")

            title   = title_el.get_text(strip=True) if title_el else card.get_text(strip=True)[:80]
            company = company_el.get_text(strip=True) if company_el else ""
            loc     = loc_el.get_text(strip=True) if loc_el else ""
            href    = link_el.get("href", "") if link_el else ""
            url     = BASE_URL + href if href.startswith("/") else href if href else BASE_URL
            desc    = desc_el.get_text(strip=True)[:600] if desc_el else ""

            if not title or len(title) < 8:
                continue

            job_id = hashlib.md5((title + company + url).encode()).hexdigest()[:16]
            jobs.append({
                "id":            job_id,
                "title":         title,
                "company":       company,
                "location":      loc,
                "contract_type": "Stage",
                "description":   desc,
                "url":           url,
                "source":        "Make Sense",
                "date_range":    "",
            })
        except Exception as e:
            logger.debug(f"Erreur parsing card Make Sense : {e}")

    logger.info(f"Make Sense : {len(jobs)} offres trouvées pour '{query}'")
    return jobs


class MakeSenseScraper:
    name = "Make Sense"

    def search_recherche(self, recherche_config: list[dict]) -> list[dict]:
        results = []
        for entry in recherche_config:
            query = entry["job_type"]
            logger.debug(f"Make Sense Recherche : '{query}'")
            jobs = _fetch_jobs(query)
            for job in jobs:
                job["date_range"] = entry.get("date_range", "")
            results.extend(jobs)
            time.sleep(1.0)
        return results

    def search_pour_plus_tard(self, ppt_config: list[dict]) -> list[dict]:
        results = []
        for entry in ppt_config:
            company  = entry["company"]
            position = entry["position"]
            query    = f"{position} {company}"
            logger.debug(f"Make Sense PPT : '{query}'")
            jobs = _fetch_jobs(query)
            for job in jobs:
                if company.lower() not in job.get("company", "").lower():
                    continue
                job["date_range"] = entry.get("date_range", "")
                results.append(job)
            time.sleep(1.0)
        return results
