"""
Filtre IA — utilise Claude pour valider chaque offre
par rapport aux critères définis dans l'Excel.

Critères globaux appliqués dans tous les cas :
  - Pas d'Europe de l'Est, pas Luxembourg, pas Belgique
  - En France : Île-de-France uniquement
  - En Afrique : seulement entreprises de premier plan
  - Pas de langue requise autre que FR/EN (même "un plus")
  - Pas de visa sponsorisé par l'entreprise nécessaire (nationalité française)
  - Poste majoritairement orienté investissements (pas risques/conformité)
"""
import json
import logging
import time
import anthropic

logger = logging.getLogger("ai_filter")

GLOBAL_CONSTRAINTS = """
Contraintes géographiques et légales (OBLIGATOIRES, non négociables) :
- Exclure tout poste en Europe de l'Est, au Luxembourg ou en Belgique.
- Si le poste est en France, n'accepter que l'Île-de-France (Paris inclus).
- Si le poste est en Afrique, n'accepter que si l'entreprise est une banque ou
  institution financière de renommée internationale (ex: Société Générale, AXA, BNP).
- Exclure tout poste dans un pays où un travailleur français aurait besoin que
  l'entreprise sponsorise son visa (ex: USA, Royaume-Uni post-Brexit pour certains).
  Si le candidat peut faire la démarche de visa seul, c'est acceptable.
- Exclure tout poste qui mentionne une langue autre que le français ou l'anglais
  comme atout ou requis (ex: "le danois est un plus" → exclure).

Format de réponse : JSON uniquement, sans texte avant/après.
{"matches": true/false, "reason": "explication courte en français"}
"""


class AIFilter:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self._cache: dict[str, bool] = {}

    def validate_recherche(self, job: dict, recherche_config: list[dict]) -> bool:
        """Valide une offre pour le flux 'Recherche entreprise'."""
        cache_key = job["id"]
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Trouve la config qui correspond au mieux au type de poste
        matching_configs = [
            c for c in recherche_config
            if c["job_type"].lower() in job.get("title", "").lower()
            or c["job_type"].lower() in job.get("description", "").lower()
        ]
        extra_criteria = matching_configs[0]["info"] if matching_configs else ""
        date_range     = matching_configs[0]["date_range"] if matching_configs else ""
        location_rules = matching_configs[0]["location"] if matching_configs else ""

        prompt = f"""
Tu es un assistant qui aide un étudiant de l'ESSEC à trouver un stage.
Évalue si cette offre d'emploi répond à ses critères.

OFFRE :
- Titre : {job.get('title', 'N/A')}
- Entreprise : {job.get('company', 'N/A')}
- Localisation : {job.get('location', 'N/A')}
- Type de contrat : {job.get('contract_type', 'N/A')}
- Description : {job.get('description', 'N/A')[:800]}

CRITÈRES SPÉCIFIQUES :
- Date de début souhaitée : {date_range}
- Critères de fond : {extra_criteria}
- Il faut que le poste soit MAJORITAIREMENT orienté investissements,
  pas risques ou conformité. Il peut y avoir de la conformité dans
  un poste d'investissement (normal), mais le cœur du poste doit
  être les investissements.

{GLOBAL_CONSTRAINTS}
"""
        result = self._call_claude(prompt)
        self._cache[cache_key] = result
        return result

    def validate_pour_plus_tard(self, job: dict, ppt_config: list[dict]) -> bool:
        """Valide une offre pour le flux 'Pour plus tard' (entreprises ciblées)."""
        cache_key = job["id"]
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Trouve l'entrée PPT correspondant à cette entreprise
        company = job.get("company", "").lower()
        matching = [
            c for c in ppt_config
            if c["company"].lower() in company or company in c["company"].lower()
        ]
        if not matching:
            # Entreprise inconnue dans la liste PPT — on rejette
            self._cache[cache_key] = False
            return False

        entry = matching[0]
        prompt = f"""
Tu es un assistant qui aide un étudiant de l'ESSEC à trouver un stage.
Évalue si cette offre correspond aux critères pour cette entreprise ciblée.

OFFRE :
- Titre : {job.get('title', 'N/A')}
- Entreprise : {job.get('company', 'N/A')}
- Localisation : {job.get('location', 'N/A')}
- Type de contrat : {job.get('contract_type', 'N/A')}
- Description : {job.get('description', 'N/A')[:800]}

CRITÈRES POUR CETTE ENTREPRISE :
- Entreprise attendue : {entry['company']}
- Poste recherché : {entry['position']}
- Infos complémentaires : {entry['info']}
- Date de début souhaitée : {entry['date_range']}
Note : si l'intitulé exact n'est pas le même mais que la description
et les responsabilités correspondent, accepter quand même.

{GLOBAL_CONSTRAINTS}
"""
        result = self._call_claude(prompt)
        self._cache[cache_key] = result
        return result

    def _call_claude(self, prompt: str) -> bool:
        """Appelle l'API Claude et retourne True si l'offre correspond."""
        for attempt in range(3):
            try:
                response = self.client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}]
                )
                text = response.content[0].text.strip()
                # Nettoie les éventuels backticks
                text = text.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(text)
                matches = parsed.get("matches", False)
                reason  = parsed.get("reason", "")
                if not matches:
                    logger.debug(f"  Rejeté par Claude : {reason}")
                return bool(matches)
            except json.JSONDecodeError as e:
                logger.warning(f"Réponse Claude non-JSON (tentative {attempt+1}) : {e}")
            except anthropic.RateLimitError:
                logger.warning("Rate limit atteint, attente 30s…")
                time.sleep(30)
            except Exception as e:
                logger.error(f"Erreur appel Claude : {e}")
                time.sleep(5)
        return False
