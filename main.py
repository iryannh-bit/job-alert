"""
Job Alert Script — Main Orchestrator
Surveille WTTJ, eFinancialCareers, Dogfinance, JobTeaser ESSEC
et les sites carrières des entreprises ciblées.
"""
import os
import logging
import sys
from datetime import datetime

from config_loader import load_config
from scrapers.wttj import WTTJScraper
from scrapers.efinancial import EFinancialScraper
from scrapers.dogfinance import DogfinanceScraper
from scrapers.makesense import MakeSenseScraper
from scrapers.company_sites import CompanyScraper
from filters.ai_filter import AIFilter
from notifier.email_sender import EmailSender
from storage.seen_jobs import SeenJobs

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

EMAIL_PPT      = os.environ.get("EMAIL_POUR_PLUS_TARD", "iryannhassim@gmail.com")
EMAIL_RECH     = os.environ.get("EMAIL_RECHERCHE",      "iryannhassim@gmail.com")
SEND_SUMMARY   = os.environ.get("SEND_SUMMARY", "false").lower() == "true"

def main():
    logger.info("═" * 60)
    logger.info(f"Démarrage — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    logger.info("═" * 60)

    # ── Config depuis l'Excel ──────────────────────────────────
    config = load_config()
    logger.info(
        f"Config chargée : {len(config['pour_plus_tard'])} entreprises PPT, "
        f"{len(config['recherche'])} types de postes Recherche"
    )

    # ── Composants partagés ───────────────────────────────────
    seen      = SeenJobs("data/seen_jobs.json")
    ai_filter = AIFilter(os.environ["ANTHROPIC_API_KEY"])
    mailer    = EmailSender()

    new_ppt    = []   # Pour plus tard
    new_rech   = []   # Recherche entreprise

    # ── Scrapers job boards ───────────────────────────────────
    board_scrapers = [
        WTTJScraper(),
        EFinancialScraper(),
        DogfinanceScraper(),
        MakeSenseScraper(),
    ]

    # JobTeaser désactivé — peut être réactivé plus tard

    # ── TYPE 2 : Recherche entreprise (job boards) ────────────
    logger.info("── Recherche entreprise : scan des job boards ──")
    for scraper in board_scrapers:
        try:
            jobs = scraper.search_recherche(config["recherche"])
            for job in jobs:
                if not seen.is_seen(job["id"]):
                    seen.mark_seen(job["id"], job, "recherche", validated=False)
                    matches, summary = ai_filter.validate_recherche(job, config["recherche"])
                    if matches:
                        job["summary"] = summary
                        seen.mark_validated(job["id"])
                        new_rech.append(job)
                        logger.info(f"  ✅ [RECH] {job['title']} @ {job['company']} ({scraper.name})")
                    else:
                        logger.info(f"  ✗ Filtré : {job['title']} @ {job['company']}")
        except Exception as e:
            logger.error(f"Erreur scraper {scraper.name} (recherche) : {e}", exc_info=True)

    # ── TYPE 1 : Pour plus tard (job boards) ─────────────────
    logger.info("── Pour plus tard : scan des job boards ──")
    for scraper in board_scrapers:
        try:
            jobs = scraper.search_pour_plus_tard(config["pour_plus_tard"])
            for job in jobs:
                if not seen.is_seen(job["id"]):
                    seen.mark_seen(job["id"], job, "pour_plus_tard", validated=False)
                    matches, summary = ai_filter.validate_pour_plus_tard(job, config["pour_plus_tard"])
                    if matches:
                        job["summary"] = summary
                        seen.mark_validated(job["id"])
                        new_ppt.append(job)
                        logger.info(f"  ✅ [PPT] {job['title']} @ {job['company']} ({scraper.name})")
                    else:
                        logger.info(f"  ✗ Filtré : {job['title']} @ {job['company']}")
        except Exception as e:
            logger.error(f"Erreur scraper {scraper.name} (PPT) : {e}", exc_info=True)

    # ── TYPE 1 : Pour plus tard (sites carrières) ─────────────
    logger.info("── Pour plus tard : scan des sites carrières ──")
    company_scraper = CompanyScraper()
    for entry in config["pour_plus_tard"]:
        company = entry["company"]
        try:
            jobs = company_scraper.scrape(entry)
            for job in jobs:
                if not seen.is_seen(job["id"]):
                    seen.mark_seen(job["id"], job, "pour_plus_tard", validated=False)
                    matches, summary = ai_filter.validate_pour_plus_tard(job, config["pour_plus_tard"])
                    if matches:
                        job["summary"] = summary
                        seen.mark_validated(job["id"])
                        new_ppt.append(job)
                        logger.info(f"  ✅ [PPT] {job['title']} @ {company} (site carrière)")
                    else:
                        logger.info(f"  ✗ Filtré : {job['title']} @ {company}")
        except Exception as e:
            logger.error(f"Erreur site carrière {company} : {e}", exc_info=True)

    # ── Envoi des alertes instantanées (PPT uniquement) ──────
    logger.info(f"── Envoi alertes instantanées : {len(new_ppt)} PPT ──")
    for job in new_ppt:
        try:
            mailer.send_alert(to=EMAIL_PPT, job=job, alert_type="pour_plus_tard")
        except Exception as e:
            logger.error(f"Échec envoi mail PPT pour {job['title']} : {e}")

    # Recherche → pas d'email instantané, seulement dans le récap quotidien
    logger.info(f"── {len(new_rech)} offres Recherche ajoutées au récap quotidien ──")

    # ── Summary quotidien (déclenché par workflow dédié) ──────
    if SEND_SUMMARY:
        logger.info("── Envoi du récap quotidien ──")
        recent_ppt  = seen.get_recent("pour_plus_tard",  hours=24)
        recent_rech = seen.get_recent("recherche",       hours=24)
        if recent_ppt:
            mailer.send_summary(to=EMAIL_PPT,  jobs=recent_ppt,  alert_type="pour_plus_tard")
        if recent_rech:
            mailer.send_summary(to=EMAIL_RECH, jobs=recent_rech, alert_type="recherche")

    # ── Sauvegarde ────────────────────────────────────────────
    seen.save()
    logger.info("═" * 60)
    logger.info("Script terminé.")
    logger.info("═" * 60)

if __name__ == "__main__":
    main()
