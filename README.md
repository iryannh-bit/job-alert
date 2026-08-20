# 💼 Job Alert — Alertes de stages automatiques

Surveille WTTJ, eFinancialCareers, Dogfinance, JobTeaser ESSEC
et les sites carrières des entreprises ciblées.
Envoie un email instantané dès qu'une nouvelle offre apparaît.

---

## Architecture

```
Toutes les 10 min (GitHub Actions) :
  → Scan WTTJ + eFinancialCareers + Dogfinance + JobTeaser ESSEC
  → Scan sites carrières (Deloitte, KPMG, EY, PwC, BDO, Mazars, etc.)
  → Filtre IA (Claude) : géo, langue, visa, investissements vs conformité
  → Mail instantané par offre

  → iryannh@gmail.com      ← "Pour plus tard" (entreprises ciblées)
  → maisondetana@gmail.com ← "Recherche entreprise" (job boards)

Tous les 2 jours à 20h :
  → Summary des offres des 48h sur les 2 boîtes
```

---

## 🚀 Installation — Guide étape par étape

### Étape 1 — Crée le repo GitHub

1. Va sur [github.com/new](https://github.com/new)
2. Nom : `job-alert` (ou ce que tu veux)
3. **Visibilité : PUBLIC** ← important pour avoir les Actions gratuites illimitées
   (tes credentials restent dans GitHub Secrets, jamais dans le code)
4. Clique "Create repository"

### Étape 2 — Upload les fichiers

1. Dans ton repo GitHub, clique "Add file" → "Upload files"
2. Glisse-dépose tout le contenu de ce dossier
3. N'oublie pas d'inclure le fichier `suivi_stages.xlsx`
4. Clique "Commit changes"

### Étape 3 — Configure les GitHub Secrets

Dans ton repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Crée ces secrets un par un :

| Secret | Valeur |
|--------|--------|
| `ANTHROPIC_API_KEY` | Ta clé API Anthropic (console.anthropic.com) |
| `JOBTEASER_EMAIL` | `b00827960@essec.edu` |
| `JOBTEASER_PASSWORD` | Ton **nouveau** mot de passe JobTeaser (après l'avoir changé) |
| `SMTP_EMAIL` | L'adresse Gmail qui envoie les alertes |
| `SMTP_PASSWORD` | App Password Gmail (voir ci-dessous) |
| `EMAIL_POUR_PLUS_TARD` | `iryannh@gmail.com` |
| `EMAIL_RECHERCHE` | `maisondetana@gmail.com` |
| `GOOGLE_DRIVE_FILE_ID` | ID de ton Excel sur Drive (optionnel) |

### Étape 4 — Crée un App Password Gmail

Pour que le script puisse envoyer des emails depuis Gmail :

1. Va sur [myaccount.google.com](https://myaccount.google.com)
2. **Sécurité** → **Validation en 2 étapes** (doit être activée)
3. **Mots de passe des applications**
4. Sélectionne "Autre (nom personnalisé)" → tape "Job Alert"
5. Copie le mot de passe de 16 caractères → c'est ton `SMTP_PASSWORD`

> Tu peux utiliser `iryannh@gmail.com` comme compte expéditeur
> (et te l'envoyer à toi-même). Il faut juste créer l'App Password sur ce compte.

### Étape 5 — Active GitHub Actions

Dans ton repo → onglet **Actions** → si un message demande de les activer, clique "Enable"

### Étape 6 — Test manuel

1. Onglet **Actions** → "Job Alert — Scan toutes les 10 min"
2. Clique **"Run workflow"** → **"Run workflow"**
3. Vérifie les logs pour t'assurer que tout tourne

---

## 📁 Mise à jour de l'Excel

**Option A — Fichier dans le repo (recommandé pour commencer)**
1. Dans ton repo GitHub → clique sur `suivi_stages.xlsx`
2. Clique l'icône crayon (Edit) ou "..." → "Upload new file"
3. Upload la nouvelle version → "Commit changes"
4. Le script utilisera la nouvelle version au prochain run

**Option B — Google Drive (plus pratique sur le long terme)**
1. Upload `suivi_stages.xlsx` sur Google Drive
2. Clic droit → Partager → "Toute personne avec le lien peut voir"
3. Copie l'ID dans l'URL : `drive.google.com/file/d/**XXXXX**/view`
4. Mets cet ID dans le secret GitHub `GOOGLE_DRIVE_FILE_ID`
5. Désormais, chaque modification du fichier sur Drive est prise en compte automatiquement

---

## ✉️ Activation des lettres de motivation (plus tard)

Quand tu seras prêt après ton stage chez Goodvest :

1. Upload ton template `.docx` dans le repo (ex: `template_lettre.docx`)
2. Dans les GitHub Secrets, mets `COVER_LETTER_ENABLED` = `true`
3. Mets ton profil dans un fichier `profile.txt` à la racine
4. Reviens ici et dis-moi — j'activerai le module de génération

---

## 🔧 Modifier les adresses email

Change simplement les secrets GitHub `EMAIL_POUR_PLUS_TARD` et `EMAIL_RECHERCHE`
dans **Settings → Secrets**. Effectif immédiatement au prochain run.

---

## 📊 Structure des fichiers

```
job-alert/
├── main.py                          ← Orchestrateur principal
├── config_loader.py                 ← Lecture de l'Excel
├── suivi_stages.xlsx                ← TON fichier de config
├── requirements.txt
├── .env.example                     ← Template variables d'env
├── scrapers/
│   ├── wttj.py                      ← Welcome to the Jungle (Algolia)
│   ├── efinancial.py                ← eFinancialCareers
│   ├── jobteaser.py                 ← JobTeaser ESSEC (authentifié)
│   ├── dogfinance.py                ← Dogfinance
│   └── company_sites.py            ← Sites carrières entreprises
├── filters/
│   └── ai_filter.py                 ← Filtre Claude (géo, visa, langue, focus)
├── notifier/
│   └── email_sender.py             ← Envoi des alertes et summary
├── storage/
│   └── seen_jobs.py                 ← Mémoire des offres déjà vues
├── data/
│   └── seen_jobs.json              ← Base de données (auto-mise à jour)
└── .github/workflows/
    ├── job_alert.yml               ← Scan toutes les 10 min
    └── summary.yml                 ← Summary bi-journalier à 20h
```
