"""
Stockage persistant des offres déjà vues.
Format JSON : { job_id: { "title", "company", "url", "type", "seen_at" } }
Le fichier est commité dans le repo GitHub après chaque run.
"""
import json
import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("seen_jobs")


class SeenJobs:
    def __init__(self, path: str):
        self.path = path
        self._data: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"Base chargée : {len(self._data)} offres connues.")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Impossible de lire seen_jobs.json : {e} — base réinitialisée.")
                self._data = {}
        else:
            logger.info("Première exécution — base vide.")
            self._data = {}

    def is_seen(self, job_id: str) -> bool:
        return str(job_id) in self._data

    def mark_seen(self, job_id: str, job: dict, alert_type: str, validated: bool = False):
        self._data[str(job_id)] = {
            "title":     job.get("title", ""),
            "company":   job.get("company", ""),
            "location":  job.get("location", ""),
            "url":       job.get("url", ""),
            "source":    job.get("source", ""),
            "type":      alert_type,
            "validated": validated,
            "seen_at":   datetime.now(timezone.utc).isoformat(),
        }

    def mark_validated(self, job_id: str):
        """Marque une offre comme validée par le filtre IA."""
        if str(job_id) in self._data:
            self._data[str(job_id)]["validated"] = True

    def get_recent(self, alert_type: str, hours: int = 24, validated_only: bool = True) -> list[dict]:
        """Retourne les offres récentes — par défaut uniquement celles validées par le filtre IA."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = []
        for job_id, meta in self._data.items():
            if meta.get("type") != alert_type:
                continue
            if validated_only and not meta.get("validated", False):
                continue
            try:
                seen_at = datetime.fromisoformat(meta["seen_at"])
                if seen_at >= cutoff:
                    result.append({**meta, "id": job_id})
            except (KeyError, ValueError):
                pass
        result.sort(key=lambda x: x.get("seen_at", ""), reverse=True)
        return result

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        logger.info(f"Base sauvegardée : {len(self._data)} offres.")
