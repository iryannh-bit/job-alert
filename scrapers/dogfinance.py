"""
Scraper Dogfinance — premier réseau socio-professionnel finance français.
Pages publiques, pas d'authentification requise.
"""
import hashlib
import logging
import time
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("scraper.dogfinance")

BASE_URL      = "https://dogfinance.com"
STAGE_URL     = f"{BASE_URL}/fr/offres/stages"
SEARCH_URL    = f"{BASE_URL}/fr/offres"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def _fetch_jobs(url: str, params: dict = None) -> list[dict]:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return _parse(r.text)
    except Exception as e:
        logger.error(f"Dogfinance erreur ({url}) : {e}")
        return []


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Structure type : divs/articles avec classe job ou offer
    selectors = [
        ".job-offer", ".offer-card", ".job-card",
        "article.job", "div.job", "[class*='JobOffer']",
        "li.offer", ".card-job",
    ]
    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            break

    # Fallback : tous les liens qui ressemblent à des offres
    if not cards:
        links = soup.select("a[href*='/offre/'], a[href*='/job/'], a[href*='/offres/']")
        for link in links:
            title = link.get_text(strip=True)
            if len(title) < 10:
                continue
            href  = link.get("href", "")
            url   = BASE_URL + href if href.startswith("/") else href
            job_id = hashlib.md5(url.encode()).hexdigest()[:16]
            jobs.append({
                "id":            job_id,
                "title":         title,
                "company":       "",
                "location":      "",
                "contract_type": "Stage",
                "description":   "",
                "url":           url,
                "source":        "Dogfinance",
                "date_range":    "",
            })
        return jobs

    for card in cards:
        try:
            title_el   = card.select_one("h2, h3, .title, [class*='title']")
            company_el = card.select_one(".company, [class*='company'], [class*='employer']")
            loc_el     = card.select_one(".location, [class*='location'], [class*='city']")
            link_el    = card.select_one("a")
            desc_el    = card.select_one(".description, [class*='description'], p")

            title   = title_el.get_text(strip=True)   if title_el   else ""
            company = company_el.get_text(strip=True) if company_el else ""
            loc     = loc_el.get_text(strip=True)     if loc_el     else ""
            href    = link_el.get("href", "")          if link_el    else ""
            url     = BASE_URL + href if href.startswith("/") else href
            desc    = desc_el.get_text(strip=True)[:800] if desc_el else ""

            if not title:
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
                "source":        "Dogfinance",
                "date_range":    "",
            })
        except Exception as e:
            logger.debug(f"Erreur parsing card Dogfinance : {e}")

    return jobs


class DogfinanceScraper:
    name = "Dogfinance"

    def search_recherche(self, recherche_config: list[dict]) -> list[dict]:
        results = []
        for entry in recherche_config:
            # Dogfinance n'est pas dans les sites de recherche, on l'ajoute
            # par défaut comme 4ème job board global
            query = entry["job_type"]
            logger.debug(f"Dogfinance Recherche : '{query}'")
            params = {"q": query, "type": "stage"}
            jobs = _fetch_jobs(SEARCH_URL, params)
            if not jobs:
                # Fallback sur la page stages générale
                jobs = _fetch_jobs(STAGE_URL)
            for job in jobs:
                job["date_range"] = entry.get("date_range", "")
            results.extend(jobs)
            time.sleep(1.0)
        return results

    def search_pour_plus_tard(self, ppt_config: list[dict]) -> list[dict]:
        results = []
        for entry in ppt_config:
            company = entry["company"]
            query   = f"{entry['position']} {company}"
            logger.debug(f"Dogfinance PPT : '{query}'")
            params = {"q": query, "type": "stage"}
            jobs = _fetch_jobs(SEARCH_URL, params)
            for job in jobs:
                if company.lower() not in job.get("company", "").lower():
                    continue
                job["date_range"] = entry.get("date_range", "")
                results.append(job)
            time.sleep(1.0)
        return results
