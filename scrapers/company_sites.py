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
        "url": "https://jobs.deloitte.fr/search?q=stage+transaction+services&type=Intern",
        "selectors": ["article.job", ".job-tile", "li.result"],
    },
    "pwc": {
        "url": "https://jobs.pwc.fr/search-results?keywords=transaction+services+stage",
        "selectors": [".job-tile", ".job-listing", "article"],
    },
    "kpmg": {
        "url": "https://kpmg.com/fr/fr/careers/search-jobs.html?keyword=transaction+services+stage",
        "selectors": [".job-card", ".job-result", "li.job"],
    },
    "ey": {
        "url": "https://careers.ey.com/ey/search/#q=transaction%20services%20stage&t=France",
        "selectors": [".job-card", ".result-item", "article"],
    },
    "bdo": {
        "url": "https://www.bdo.fr/fr-fr/offres-de-missions?keyword=transaction+stage",
        "selectors": [".job-card", ".mission-card", "article"],
    },
    "forvis mazars": {
        "url": "https://www.forvismazars.com/fr/fr/careers/job-search?q=transaction+services+stage",
        "selectors": [".job-card", ".vacancy-item", "article"],
    },
    "mazars": {
        "url": "https://www.forvismazars.com/fr/fr/careers/job-search?q=transaction+services+stage",
        "selectors": [".job-card", ".vacancy-item", "article"],
    },
    "accenture": {
        "url": "https://www.accenture.com/fr-fr/careers/jobsearch?jk=stage+m%26a+tech",
        "selectors": [".cmp-job-list-item", ".job-card", "li.job"],
    },
    "natixis": {
        "url": "https://jobs.natixis.com/search?q=stage+M%26A&type=Internship",
        "selectors": [".job-card", ".result-row", "article"],
    },
    "ubs": {
        "url": "https://jobs.ubs.com/TGWebHost/searchjobs.aspx?Keywords=ESG+analyst+internship&Country=France",
        "selectors": [".job-result", ".position-item", "tr.job"],
    },
    "orange": {
        "url": "https://emploi.orange.fr/offres?text=M%26A+stage&type=internship",
        "selectors": [".job-card", ".offer-item", "article"],
    },
    "accuracy": {
        "url": "https://accuracy.com/fr/rejoindre-accuracy/offres-emploi/",
        "selectors": [".job-item", ".offer", "article", "li"],
    },
    "iad": {
        "url": "https://recrutement.iadfrance.fr/nos-offres",
        "selectors": [".job-card", ".offer-item", "article", "li.offer"],
    },
    "carbone4": {
        "url": "https://www.carbone4.com/rejoindre-carbone4",
        "selectors": [".job", ".position", "article", "li"],
    },
    "eight advisory": {
        "url": "https://www.eight-advisory.com/fr/nous-rejoindre/nos-offres",
        "selectors": [".job-item", ".offer", "article"],
    },
    "amethis": {
        "url": "https://www.amethis.co/fr/join-us/",
        "selectors": [".job", ".position", "article", "li"],
    },
    "investisseurs & partenaires": {
        "url": "https://www.ietp.com/fr/nous-rejoindre",
        "selectors": [".job", ".offer", "article", "li"],
    },
    "i&p": {
        "url": "https://www.ietp.com/fr/nous-rejoindre",
        "selectors": [".job", ".offer", "article", "li"],
    },
    "axian": {
        "url": "https://www.axian-group.com/en/careers/",
        "selectors": [".job-card", ".career-item", "article", "li"],
    },
    "iptp": {
        # IPTP publie uniquement sur WTTJ — site carrière minimal
        "url": "https://www.inflexionpointspartners.com/fr/join-us",
        "selectors": [".job", ".offer", "article", "li", "a"],
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
