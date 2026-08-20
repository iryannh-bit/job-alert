"""
Scraper eFinancialCareers — parsing HTML + JSON-LD structuré.
"""
import hashlib
import logging
import time
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("scraper.efinancial")

BASE_URL = "https://www.efinancialcareers.fr"
SEARCH_URL = f"{BASE_URL}/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _search(query: str, rows: int = 25) -> list[dict]:
    params = {
        "q":            query,
        "searchType":   "jobTitle",
        "countryCode":  "FR",
        "rows":         rows,
    }
    try:
        r = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return _parse_results(r.text)
    except Exception as e:
        logger.error(f"eFinancialCareers erreur pour '{query}' : {e}")
        return []


def _parse_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Les offres sont dans des articles avec data-job-id
    for article in soup.select("article[data-job-id], div[data-job-id]"):
        try:
            job_id  = "efc_" + article.get("data-job-id", "")
            title   = article.select_one("[data-bind*='title'], h2, h3")
            company = article.select_one("[data-bind*='company'], .job-company")
            location = article.select_one("[data-bind*='location'], .job-location")
            link    = article.select_one("a[href*='/job/']")

            title_text   = title.get_text(strip=True)   if title    else ""
            company_text = company.get_text(strip=True) if company  else ""
            loc_text     = location.get_text(strip=True) if location else ""
            url = BASE_URL + link["href"] if link and link.get("href","").startswith("/") else (link["href"] if link else "")

            desc_elem = article.select_one(".job-description, [data-bind*='description']")
            desc = desc_elem.get_text(strip=True)[:800] if desc_elem else ""

            job_hash = hashlib.md5(job_id.encode()).hexdigest()[:16]
            jobs.append({
                "id":            job_hash,
                "title":         title_text,
                "company":       company_text,
                "location":      loc_text,
                "contract_type": "Stage",
                "description":   desc,
                "url":           url,
                "source":        "eFinancialCareers",
                "date_range":    "",
            })
        except Exception as e:
            logger.debug(f"Erreur parsing article eFC : {e}")

    # Fallback : chercher via les liens de job si la structure HTML a changé
    if not jobs:
        for link in soup.select("a[href*='/job/']"):
            try:
                href  = link.get("href", "")
                title = link.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                url = BASE_URL + href if href.startswith("/") else href
                job_id = hashlib.md5(href.encode()).hexdigest()[:16]
                jobs.append({
                    "id":            job_id,
                    "title":         title,
                    "company":       "",
                    "location":      "",
                    "contract_type": "Stage",
                    "description":   "",
                    "url":           url,
                    "source":        "eFinancialCareers",
                    "date_range":    "",
                })
            except Exception:
                pass

    return jobs


class EFinancialScraper:
    name = "eFinancialCareers"

    def search_recherche(self, recherche_config: list[dict]) -> list[dict]:
        results = []
        for entry in recherche_config:
            if "efinancialcareers" not in " ".join(entry.get("sites", [])).lower():
                continue
            query = f"stage {entry['job_type']}"
            logger.debug(f"eFC Recherche : '{query}'")
            jobs = _search(query)
            for job in jobs:
                job["date_range"] = entry.get("date_range", "")
            results.extend(jobs)
            time.sleep(1.0)
        return results

    def search_pour_plus_tard(self, ppt_config: list[dict]) -> list[dict]:
        results = []
        for entry in ppt_config:
            query = f"stage {entry['position']} {entry['company']}"
            logger.debug(f"eFC PPT : '{query}'")
            jobs = _search(query, rows=10)
            for job in jobs:
                job["date_range"] = entry.get("date_range", "")
            results.extend(jobs)
            time.sleep(1.0)
        return results
