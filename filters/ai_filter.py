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
Contraintes OBLIGATOIRES (non négociables) — rejeter si l'une n'est pas respectée :

1. TYPE DE CONTRAT : Stage uniquement (internship/stage). Rejeter tout CDI, CDD, alternance, VIE, freelance.
   Si le type de contrat est inconnu mais que le titre ou la description ne mentionne pas "stage" ou "intern", rejeter.

2. GÉOGRAPHIE :
   - Si le poste est en France : Île-de-France UNIQUEMENT (Paris, 92, 93, 94, 78, 91, 95, 77). Rejeter Rennes, Lyon, Bordeaux, Marseille, etc.
   - Si la localisation est inconnue ou vide ET que l'entreprise est française, supposer Paris/IDF → accepter.
   - Si le poste est en Afrique : n'accepter que si l'entreprise est une institution financière de renommée internationale.
   - Rejeter tout poste en Europe de l'Est, Luxembourg, Belgique.
   - Rejeter tout poste nécessitant un visa sponsorisé par l'entreprise.

3. LANGUE : Rejeter si une langue autre que français ou anglais est mentionnée comme requise ou "un plus".

4. CONTENU VALIDE : Rejeter si l'offre ressemble à une page de navigation, mentions légales, politique de confidentialité, numéro de téléphone, adresse email, ou tout autre contenu non-pertinent. Le titre doit ressembler à un vrai intitulé de poste.

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

RÈGLES POUR LES ENTREPRISES CIBLÉES (plus souples que la recherche générale) :
- Accepter si l'offre est dans le domaine finance/M&A/conseil/investissement même si l'intitulé exact diffère.
- Accepter si la description correspond à l'esprit du poste recherché, même si quelques mots-clés manquent.
- En cas de doute raisonnable, préférer accepter plutôt que rejeter (le candidat préfère voir l'offre).
- Rejeter seulement si c'est clairement hors sujet (ex: poste RH, IT pur, commercial terrain) ou hors contraintes géo/contrat.

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
