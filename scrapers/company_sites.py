"""
Scraper des sites carrières des entreprises ciblées (feuille "Pour plus tard").
Chaque entreprise a son propre URL et sa propre structure.
Le fallback sur job boards est géré dans main.py.
"""
import hashlib
import logging
import time
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("scraper.company")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# ── Registre des URLs de carrières ───────────────────────────────────────────
# Format : "Nom entreprise" (minuscules) → URL page offres + sélecteur CSS
# Ajouter ici de nouvelles entreprises au besoin.

COMPANY_REGISTRY: dict[str, dict] = {
    "deloitte": {
        "url": "https://www.deloitte.com/fr/fr/careers/content/job/results.html",
        "selectors": ["article.job", ".job-tile", "li.result", ".job-card"],
    },
    "pwc": {
        "url": "https://carrieres.pwc.fr/fr/stage-offres.html",
        "selectors": [".job-tile", ".job-listing", "article", ".job-card"],
    },
    "kpmg": {
        "url": "https://emplois.kpmg.fr/recherche-d%27offres?acm=ALL&alrpm=ALL&ascf=[{%22key%22:%22custom_fields.CareerLevel%22,%22value%22:%22Etudiants%22}]",
        "selectors": [".job-card", ".job-result", "li.job", "article"],
    },
    "ey": {
        "url": "https://eyglobal.yello.co/job_boards/c1riT--B2O-KySgYWsZO1Q",
        "selectors": [".job-card", ".result-item", "article", "li"],
    },
    "bdo": {
        "url": "https://recrutement.bdo.fr/",
        "selectors": [".job-card", ".mission-card", "article", "li"],
    },
    "forvis mazars": {
        "url": "https://recrutement-fr.forvismazars.com/offres-emploi?contract=stage",
        "selectors": [".job-card", ".vacancy-item", "article", "li"],
    },
    "mazars": {
        "url": "https://recrutement-fr.forvismazars.com/offres-emploi?contract=stage",
        "selectors": [".job-card", ".vacancy-item", "article", "li"],
    },
    "accenture": {
        "url": "https://www.accenture.com/fr-fr/careers/jobsearch",
        "selectors": [".cmp-job-list-item", ".job-card", "li.job", "article"],
    },
    "natixis": {
        "url": "https://recrutement.natixis.com/nos-offres-demploi?external=false",
        "selectors": [".job-card", ".result-row", "article", "li"],
    },
    "ubs": {
        "url": "https://jobs.ubs.com/TGNewUI/Search/Home/Home?partnerid=25008&siteid=5176",
        "selectors": [".job-result", ".position-item", "tr.job", "article"],
    },
    "orange": {
        "url": "https://orange.jobs/fr/fr/search-results",
        "selectors": [".job-card", ".offer-item", "article", "li"],
    },
    "accuracy": {
        "url": "https://www.accuracy.com/fr/nous-rejoindre/",
        "selectors": [".job-item", ".offer", "article", "li", "a[href*='emploi']"],
    },
    "iad": {
        "url": "https://www.welcometothejungle.com/fr/companies/iad/jobs",
        "selectors": [".job-card", ".offer-item", "article", "li.offer"],
    },
    "carbone4": {
        "url": "https://carbone4.com/fr/jobs",
        "selectors": [".job", ".position", "article", "li", "a[href*='job']"],
    },
    "eight advisory": {
        "url": "https://www.8advisory.com/emplois/",
        "selectors": [".job-item", ".offer", "article", "li"],
    },
    "amethis": {
        "url": "https://www.amethis.com/en/careers/",
        "selectors": [".job", ".position", "article", "li", "a[href*='job']"],
    },
    "investisseurs & partenaires (i&p)": {
        "url": "https://www.ietp.com/fr/content/recrutement",
        "selectors": [".job", ".offer", "article", "li", "a[href*='emploi']"],
    },
    "i&p": {
        "url": "https://www.ietp.com/fr/content/recrutement",
        "selectors": [".job", ".offer", "article", "li", "a[href*='emploi']"],
    },
    "axian": {
        "url": "https://axian-group.csod.com/ux/ats/careersite/1/home?c=axian-group",
        "selectors": [".job-card", ".career-item", "article", "li", ".requisition"],
    },
    "iptp": {
        "url": "https://www.welcometothejungle.com/fr/companies/inflexion-points-technology/jobs",
        "selectors": [".job", ".offer", "article", "li", "a"],
    },
    "ecofi": {
        "url": "https://jobs.makesense.org/fr/projects/ecofi-5588",
        "selectors": [".job-card", ".offer", "article", "li"],
    },
    "bnp paribas cardif": {
        "url": "https://www.bnpparibascardif.com/nous-rejoindre/nos-offres-demploi/?keywords=&type%5B%5D=stage",
        "selectors": [".job-card", ".offer-item", "article", "li"],
    },
}


def _generic_scrape(url: str, selectors: list[str], company_name: str, source_label: str) -> list[dict]:
    """Scrape générique : essaie chaque sélecteur jusqu'à trouver des résultats."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as e:
        logger.warning(f"Impossible d'accéder à {url} : {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    jobs = []

    for selector in selectors:
        cards = soup.select(selector)
        if not cards:
            continue
        for card in cards:
            try:
                title_el = card.select_one("h2, h3, h4, .title, [class*='title'], strong")
                link_el  = card.select_one("a[href]") or (card if card.name == "a" else None)
                desc_el  = card.select_one("p, .desc, [class*='desc'], [class*='summary']")

                title = title_el.get_text(strip=True) if title_el else card.get_text(strip=True)[:80]
                href  = link_el.get("href", "") if link_el else ""
                desc  = desc_el.get_text(strip=True)[:600] if desc_el else ""

                if not title or len(title) < 8:
                    continue
                # Ignore les entrées non-pertinentes
                NOISE_WORDS = [
                    "accueil", "menu", "contact", "home", "back", "legal", "privacy",
                    "cookie", "terms", "politique", "mentions légales", "confidentialité",
                    "copyright", "sitemap", "newsletter", "linkedin", "twitter", "facebook",
                    "instagram", "youtube", "commitment", "cluster", "property", "energy",
                    "digibank", "fintech", "propert", "services", "group", "about",
                    "découvrir", "nos valeurs", "notre histoire", "press", "media",
                ]
                if any(x in title.lower() for x in NOISE_WORDS):
                    continue
                # Rejeter les numéros de téléphone, emails, et titres trop longs (nav)
                import re
                if re.match(r'^\+?\d[\d\s\-\.]{6,}$', title):
                    continue
                if "@" in title or "http" in title:
                    continue
                if len(title) > 120:
                    continue
                    continue

                # Construction URL absolue
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    full_url = f"{parsed.scheme}://{parsed.netloc}{href}"
                else:
                    full_url = url

                job_id = hashlib.md5((title + company_name + href).encode()).hexdigest()[:16]
                jobs.append({
                    "id":            job_id,
                    "title":         title,
                    "company":       company_name,
                    "location":      "",
                    "contract_type": "Stage",
                    "description":   desc,
                    "url":           full_url,
                    "source":        source_label,
                    "date_range":    "",
                })
            except Exception as e:
                logger.debug(f"Erreur card {company_name} : {e}")
        if jobs:
            break   # On s'arrête au premier sélecteur qui donne des résultats

    return jobs


class CompanyScraper:
    """Scrape les sites carrières des entreprises de 'Pour plus tard'."""

    def scrape(self, entry: dict) -> list[dict]:
        """
        Scrape le site carrière de l'entreprise.
        Retourne une liste d'offres brutes (filtrage IA fait dans main.py).
        """
        company  = entry["company"]
        company_key = company.lower()

        # Cherche la config dans le registre
        registry_entry = None
        for key, val in COMPANY_REGISTRY.items():
            if key in company_key or company_key in key:
                registry_entry = val
                break

        if not registry_entry:
            logger.debug(f"Pas de config carrière pour '{company}' — ignoré (couvert par job boards).")
            return []

        url       = registry_entry["url"]
        selectors = registry_entry["selectors"]
        source    = f"Site carrière {company}"

        logger.debug(f"Scraping {company} → {url}")
        jobs = _generic_scrape(url, selectors, company, source)
        time.sleep(2.0)   # Respecter le rate limiting

        for job in jobs:
            job["date_range"] = entry.get("date_range", "")

        if not jobs:
            logger.debug(f"Aucune offre trouvée sur le site carrière de {company}.")

        return jobs
