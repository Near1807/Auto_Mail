# Auto Mail

Application de bureau Windows pour envoyer des mails en série depuis Gmail, avec un fichier
de suivi par campagne. Un seul fichier `AutoMail.exe`, rien d'autre à installer.

- **Campagnes** : un message, ses destinataires et un CSV de suivi. Une adresse marquée
  « Envoyé » dans le suivi ne reçoit jamais le même mail deux fois ; une adresse en
  « Erreur » est retentée.
- **Destinataires** : colle les adresses dans n'importe quel format (une par ligne, `,` / `;`,
  liste Python, `Nom <a@b.be>`, `mailto:`), ou un tableau copié d'Excel : ses colonnes
  deviennent des variables `{prenom}`, `{nom}`…
- **Message** : texte, HTML (éditeur avec coloration) ou visuel, aperçu par destinataire,
  modèles, pièces jointes par glisser-déposer. Brouillon enregistré automatiquement.
- **Envoi** : test vers soi, récapitulatif, progression en direct, pause / reprise /
  annulation, libellé Gmail (créé s'il n'existe pas, sous-libellés avec `/`).
- **Suivi** : tableau triable et filtrable, colonne réponse éditable, export CSV,
  « Vérifier les réponses » qui lit les fils du libellé dans Gmail.

## Installer et utiliser

1. Télécharge `AutoMail.exe` depuis la page **Releases** du dépôt.
2. Double-clic. Au premier lancement, Windows SmartScreen peut afficher « Windows a protégé
   votre ordinateur » : l'exe n'est pas signé (un certificat de signature est payant).
   Clique sur **Informations complémentaires** puis **Exécuter quand même**.
3. **Réglages** : ton adresse Gmail, ton nom, et un
   [mot de passe d'application](https://myaccount.google.com/apppasswords) (16 caractères,
   la validation en deux étapes doit être activée sur le compte). Puis **Tester la connexion**.

Le mot de passe est rangé dans le **Gestionnaire d'identification Windows** (service
`AutoMail`), jamais dans un fichier. Gmail limite l'envoi à environ 500 destinataires par jour.

### Où sont mes données

Tout est dans `%APPDATA%\AutoMail` (jamais à côté de l'exe) :

| Chemin | Contenu |
| --- | --- |
| `campagnes\<campagne>\suivi.csv` | le suivi : `email;status;reponse;date;objet;erreur` (UTF-8 avec BOM, s'ouvre dans Excel) |
| `campagnes\<campagne>\message.json` | le brouillon de la campagne |
| `campagnes\<campagne>\pj\` | les pièces jointes |
| `settings.json` | adresse, nom affiché, délai, thème (sans mot de passe) |
| `logs\automail.log` | le journal, utile en cas de problème |

Tes anciens fichiers `suivi_envois.csv` (`email;status;reponse`) s'importent depuis
**Campagnes → Importer un CSV**. Les colonnes que tu ajoutes à la main dans Excel sont
conservées. Si le CSV est ouvert dans Excel pendant un envoi, l'envoi continue et l'appli
te prévient ; le suivi est écrit dès que le fichier est libéré.

## Développement

Prérequis : Python 3.11+ et Node 20+.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (macOS/Linux : source .venv/bin/activate)
pip install -r requirements-dev.txt
npm --prefix frontend ci
```

Deux terminaux :

```bash
uvicorn api.main:app --port 8765 --reload     # le back
npm --prefix frontend run dev                 # le front : http://localhost:5173
```

Le front de dev relaie `/api` vers le port 8765. Pour essayer sans rien envoyer, lance le
back en **mode démo** (faux Gmail, n'importe quel mot de passe sauf « faux » ; les adresses
contenant « bounce » échouent) :

```bash
set AUTOMAIL_DEMO=1               # PowerShell : $env:AUTOMAIL_DEMO=1
set AUTOMAIL_DATA_DIR=%TEMP%\automail-demo
uvicorn api.main:app --port 8765
```

Tests (aucun vrai mail n'est jamais envoyé : SMTP et IMAP sont simulés, le réseau est bloqué) :

```bash
python -m pytest
```

Organisation :

| Dossier | Rôle |
| --- | --- |
| `core/` | logique métier, sans interface : adresses, CSV de suivi, messages, Gmail, envoi |
| `api/` | API FastAPI ; sert aussi le front compilé |
| `frontend/` | React + Vite + TypeScript + Tailwind |
| `desktop/`, `automail.py` | fenêtre pywebview, instance unique, `--self-test` |
| `AutoMail.spec` | configuration PyInstaller |
| `scripts/make_icon.py` | régénère `assets/icon.ico` (nécessite Pillow) |

## Construire l'exe en local (Windows)

```bash
npm --prefix frontend ci
npm --prefix frontend run build
pip install -r requirements-build.txt
pyinstaller AutoMail.spec --noconfirm
dist\AutoMail.exe --self-test     # vérifie l'exe, code de sortie 0 = OK
```

L'exe est dans `dist\AutoMail.exe`. `--self-test` démarre le serveur interne, vérifie
`/api/health`, le front embarqué, keyring et pywebview, puis quitte ; le détail est dans
`%APPDATA%\AutoMail\logs\automail.log`. L'exe n'ayant pas de console, en PowerShell :
`(Start-Process dist\AutoMail.exe -ArgumentList --self-test -Wait -PassThru).ExitCode`.

## Publier une version

Le workflow `.github/workflows/build.yml` tourne sur `windows-latest` : build du front,
`pytest`, PyInstaller, puis `AutoMail.exe --self-test`.

- **Tag `v*`** : l'exe est attaché à une Release GitHub nommée d'après le tag, et la version
  affichée par l'appli est celle du tag.

  ```bash
  git checkout main && git pull
  git tag v1.0.0
  git push origin v1.0.0
  ```

  Quelques minutes plus tard : **Releases → Auto Mail v1.0.0 → AutoMail.exe**.
- **Lancement manuel** (Actions → Build AutoMail.exe → Run workflow) et **pull requests vers
  `main`** : l'exe est disponible en artefact `AutoMail-exe` en bas de la page du run.
