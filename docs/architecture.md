# Architecture

Ce document décrit l'organisation du code et les décisions structurantes du projet, avec leur raison. Le fonctionnement côté utilisateur (format des notes, génération des TODO…) est décrit dans le [README](../README.md) ; le suivi des évolutions se fait dans les [issues](https://github.com/tanguycadoux/Application-gestion-generale/issues) GitHub.

## Contexte

- Application **locale et mono-utilisateur** : pas d'authentification, réglages Django non durcis (`DEBUG`, `SECRET_KEY` en dur).
- Django, SQLite, rendu côté serveur. Front sans Node ; seule étape de build, la feuille Tailwind (voir la section Front).

## Front

- Rendu côté serveur par les gabarits Django ; pas d'étape de build JS.
- **Tailwind CSS** v4 pour le style, **Material Symbols Rounded** (Google Fonts) pour les icônes, **htmx** pour les mises à jour partielles. Le détail des versions et des points de chargement est dans le README.
- **Aucune ressource externe** (#217) : les notes sont privées, et le navigateur ne doit contacter aucun serveur tiers. La feuille Tailwind est compilée en local par `django-tailwind-cli` (CLI autonome de Tailwind, version épinglée par `TAILWIND_CLI_VERSION`, sans Node) depuis `assets/css/source.css`, dans `static/css/tailwind.css`, non versionnée ; la CI la construit dans un job à part. htmx est embarqué dans `static/vendor/htmx/`, avec sa licence et un README (source, empreinte d'intégrité), et chargé une fois par le gabarit de base. Une bibliothèque front s'ajoute de la même façon (CodeMirror, #89). Le téléchargement du CLI de Tailwind est une étape d'installation, pas une requête de l'application. Reste la police d'icônes, remplacée par des SVG locaux dans #218.
- Règle de style : tout en classes Tailwind (#79) ; CSS propre réservé à ce que Tailwind ne couvre pas : le HTML produit par le Markdown (`.rendered-content`, callouts) et les animations des alertes créées en JavaScript (bloc `@layer components` de `assets/css/source.css`). L'apparence des alertes est en classes Tailwind dans le script ; leurs boutons reprennent les classes des variantes du composant `button`, transmises par le gabarit de base (`{% button_variants_json %}`). Le détail est dans le README. Les éléments d'interface récurrents sont des composants partagés : balises d'inclusion de `core/templatetags/ui.py` (`{% load ui %}`), gabarits dans `core/templates/core/components/` (principes dans la section « Composants d'interface » plus bas). Le thème Tailwind (couleurs de Tailwind, toutes émises par `theme(static)`) et les styles de base sont dans `assets/css/source.css`.

## Apps et dépendances

```
app_gestion/   configuration : settings, urls
core/          éléments communs : Project, Subject, Tag, AppError,
               page d'accueil, gabarit de base, statiques communs
images/        modèle Image et import des images
note_taking/   notes, analyse qmd, rendu, recherche, pages d'images
todolist/      TODO
```

Sens des dépendances (une flèche signifie « importe ») :

```
todolist ──► note_taking ──► images ──► core
   │              │                      ▲
   └──────────────┴──────────────────────┘
```

- `core` ne dépend d'aucune app (#179). Ce qu'il affiche des autres apps, chacune le déclare dans son `AppConfig`, et `core/app_registry.py` le lit dans l'ordre d'`INSTALLED_APPS` :
  - `home_link` : son entrée dans le menu de l'accueil général ;
  - `project_usages` : ce qui utilise un projet chez elle (chemin de comptage depuis `Project`, libellés), pour l'afficher dans la liste des projets et refuser la suppression d'un projet utilisé. On compte des notes, pas des note parts : c'est pourquoi le chemin est déclaré plutôt que déduit des relations du modèle.
- `images` ne connaît pas les notes : c'est `note_taking` qui référence les images. L'app reste ainsi utilisable par un futur éditeur d'images.
- `note_taking` ne connaît pas les tâches (#179). Après le recalcul des note parts d'une note, elle émet le signal `note_parts_processed` (`note_taking/signals.py`), dans la même transaction ; `todolist` l'écoute (`todolist/receivers.py`) et crée les tâches. `todolist` dépend donc de `note_taking` : le signal, `NotePart`, et `Note` pour le lien vers la note d'origine d'une tâche.
- Ce sens est vérifié par un test (`core/tests/test_dependencies.py`) : imports Python et noms d'URL cités dans les gabarits, hors tests et migrations.

## Organisation de `note_taking`

| Module | Rôle |
|---|---|
| `qmd/parser.py` | analyse du texte d'une note en note parts (`ParsedNote`, `ParsedPart`) ; **sans accès à la base** |
| `qmd/files.py` | lecture des fichiers `.qmd`, séparation du bloc d'en-tête (`split_front_matter`) |
| `services.py` | import, mise à jour, génération des note parts et des liens vers les images (accès à la base) |
| `signals.py` | `note_parts_processed`, émis après le recalcul des note parts (tâches issues des notes) |
| `rendering.py` | rendu HTML : Markdown, références d'images, callouts Quarto |
| `exceptions.py` | erreurs métier (`NoteError` et sous-classes) |
| `management/commands/reprocess_notes.py` | recalcul des note parts de toutes les notes |

Les vues sont fines : elles délèguent aux services et n'attrapent que les erreurs métier.

## Modèle de données

```
Note ──< NotePart >── Project          (core)
           │  │  └──── Subject (option) (core)
           │  └──<>── Tag              (core)
           └────<>─── Image            (images), via NotePartImageLink

Todo >── Project, Todo >─< Tag, Todo >── Todo (parent)
```

- **`Note`** : une note par jour (`date` unique) ; `body` contient le texte de la note.
- **`NotePart`** : morceau de note partageant projet, sujet et tags. **Données dérivées** de `Note.body`.
- **`Project`, `Subject`, `Tag`** : partagés par les notes et les TODO, noms uniques.
- **`Image`** : nom de fichier d'origine (unique, sert de référence dans les notes), fichier affiché, source éditable optionnelle.

## Décisions

### La base fait foi, le qmd est un format d'échange (#24)

`Note.body` est le texte de la note, **sans bloc d'en-tête** (`---` / `date: …` / `---`). La date est celle de `Note.date`. Le bloc d'en-tête n'est lu qu'à l'import (vérification de la date) et sera régénéré à l'export (#64). Dans le formulaire web, un bloc d'en-tête éventuel est retiré, ou refusé si sa date diffère.

On ne stocke pas la note sous forme structurée (arbre de sections) : le découpage en note parts perd de l'information (ordre, origine des tags, mise en forme) et ne permet pas de régénérer la note. Le texte reste la source.

Export et import (#64, #114) : l'export produit une archive zip à la disposition d'un dossier Quarto (`AAAA-MM-JJ.qmd` à la racine, `images/<nom>`), qui forme un projet Quarto valide une fois dézippée ; chaque fichier est généré depuis la base (`note_taking/qmd/export.py`). Un seul formulaire d'import (`note_taking/importing.py`) accepte plusieurs fichiers et traite chacun selon son type : un `.zip` est l'archive de l'export, un `.qmd` une note, une image une image. Les images sont importées avant les notes, qui les citent. La base fait foi : une image déjà présente sous ce nom est gardée (le fichier importé est écarté, sans doublon, le nom étant unique) ; une note dont la date existe déjà n'est jamais remplacée sans confirmation : pour l'instant elle est ignorée et signalée dans le compte rendu (choix entre les deux versions : #115). Le remplacement volontaire d'une note par son fichier source reste sur la page de la note.

### Les note parts sont dérivées et recalculées

`process_note_parts` supprime et recrée les note parts d'une note, avec leurs liens (tags, images), à chaque enregistrement (import, mise à jour, formulaire). Conséquences :

- aucune donnée saisie ne doit être rattachée à une note part, car elle serait perdue au prochain enregistrement ;
- après une évolution du parseur, `python manage.py reprocess_notes` recalcule toutes les notes (`--dry-run` pour simuler).

### TODO générées depuis les notes

Les TODO sont créées par `todolist`, à l'écoute du signal `note_parts_processed` (voir « Apps et dépendances »). Une TODO générée est identifiée par sa date et son texte, pas par une clé étrangère vers sa note part (qui est recréée à chaque enregistrement). Modifier la ligne dans la note crée une nouvelle TODO ; l'ancienne est conservée. Le sujet est en pause.

### Projets, sujets et tags partagés (#19, #20)

- Un même modèle pour les notes et les TODO, fusionnés par nom lors de la migration.
- Un **sujet est global**, indépendant des projets (« Calcul thermique » peut apparaître dans plusieurs projets).
- La casse est respectée (« Thermique » ≠ « thermique »).
- Sujets et tags devenus inutilisés restent en base, mais ne sont pas proposés dans la recherche.
- Les tags vides (`tags: []`) sont ignorés.

### Images (#25, #26)

- Modèle dans l'app `images` ; les **pages restent dans la prise de notes**.
- Une image est référencée dans une note par son **nom de fichier**, quel que soit le dossier écrit. À l'analyse, la référence devient `image:<pk>` dans le contenu de la note part.
- Le **format** (vectoriel ou matriciel) se déduit de l'extension du fichier (`is_vector`), l'**origine** de la présence d'une source (`is_editable`) : ce sont deux notions indépendantes, sans champ dédié.
- Le lien vers les images est porté par la **note part**, là où l'image est utilisée : on sait dans quel projet, sujet et avec quels tags elle apparaît. `Note.images` en est déduit.

### Suppression protégée

Un objet utilisé ne peut pas être supprimé (`on_delete=PROTECT`) :

- un **projet** utilisé par une note part ou une TODO ;
- un **sujet** utilisé par une note part ;
- une **image** utilisée par une note part (via `NotePartImageLink`).

Django refuse la suppression (`ProtectedError`) et l'admin liste les éléments concernés.

Dans l'interface, une image se supprime depuis sa page de détail (#85) : le bouton est désactivé, avec la raison, tant que l'image est utilisée. Le service `images.services.delete_image` s'appuie sur la même protection : il traduit la `ProtectedError` en erreur métier (`ImageInUseError`), sans connaître les apps qui utilisent les images, et n'efface les fichiers qu'une fois la suppression validée en base.

### Analyse des notes

Les règles d'analyse sont décrites dans le README. Choix notables :

- le texte placé avant le premier projet (`#`) est ignoré (à revoir, #36) ;
- les callouts Quarto sont conservés dans le contenu et rendus en encadrés à la manière de Quarto (#39) ;
- l'indentation du contenu est conservée (#34).

### Erreurs métier

`core.exceptions.AppError` est la base des erreurs dont le message est destiné à l'utilisateur (`NoteError`, `ImageError` et leurs sous-classes). Les vues n'attrapent que celles-ci ; toute autre exception est un bug et n'est pas masquée. Un import de plusieurs fichiers traite chaque fichier indépendamment, en tout ou rien.

### Champs texte

Aucun champ texte n'est nullable : chaîne vide par défaut (#48, règle ruff `DJ001`).

### Composants d'interface (#78)

Les éléments d'interface récurrents (boutons, liens du menu, listes de tags…) sont des composants partagés, définis une fois dans `core` :

- **Mécanisme** : des balises d'inclusion Django (`inclusion_tag`) dans `core/templatetags/ui.py`, chargées avec `{% load ui %}`. Chaque balise prépare le contexte et rend son gabarit, dans `core/templates/core/components/`. Elles ont été préférées aux `{% include … with … %}` : l'appel est plus court, les paramètres sont nommés et vérifiés (un paramètre inconnu est une erreur de gabarit), et une valeur invalide, comme une variante qui n'existe pas, peut être refusée.
- **Un composant par rôle, pas par apparence** : deux éléments qui se comportent de la même façon pour l'utilisateur sont un seul composant. Par exemple, `button` rend un `<a>` quand on lui donne un `href` et un `<button>` sinon : la balise HTML découle de l'action (naviguer ou envoyer un formulaire), elle n'est pas un choix à faire à chaque appel. Un composant à part se justifie par un comportement propre : `nav_link` calcule lui-même son état actif à partir de la page courante.
- **L'apparence passe par `variant`** (`primary`, `danger`, `ghost`…). Les classes Tailwind de chaque variante sont écrites en entier, dans le gabarit ou dans un dictionnaire de `ui.py`, jamais construites par morceaux.
- **Une API minimale** : peu de paramètres, avec des valeurs par défaut qui couvrent l'usage courant. Le libellé est le premier argument, positionnel ; tout le reste est nommé. Un paramètre ou une variante ne s'ajoute que lorsqu'une page en a besoin, pas par anticipation.
- **Accessibilité intégrée** : un élément réduit à une icône reçoit son libellé en `aria-label`, et le lien de menu actif reçoit `aria-current="page"`.
- **Tests** : chaque composant a des tests du HTML rendu (`core/tests/test_components.py`), qui servent aussi de référence pour ses classes.

## Conventions de travail

### Tests

- `python manage.py test` ; tests dans un paquet `tests/` par app.
- **Tests d'abord** : avant de modifier un comportement, un commit ajoute les tests du comportement attendu, marqués `@unittest.expectedFailure` ; le commit de correction retire le décorateur.
- **Élagage en fin de milestone** : une issue, traitée en dernier, repasse sur les tests ajoutés pendant le milestone. Elle supprime les tests d'absence d'une chose retirée qui n'a pas de raison de revenir (un bouton, un panneau), garde ceux qui protègent une règle transversale ou une faille (ils échoueraient si un nouveau gabarit l'enfreignait), et fusionne les tests redondants.
- Le parseur est couvert par une note d'exemple (`note_taking/tests/data/exemple.qmd`) dont le résultat attendu est figé (`exemple.json`, régénérable avec `UPDATE_GOLDEN=1`, diff à relire).

### Outillage et CI

- `ruff` (lint et formatage, configuration dans `pyproject.toml`), `mypy` avec `django-stubs` (`mypy.ini`).
- La CI GitHub Actions lance `ruff check`, `ruff format --check`, `mypy`, `makemigrations --check` et les tests à chaque PR.
- `main` est protégée : une PR ne peut être mergée que si la CI passe et que la branche est à jour.

### Git

- Une branche par issue, partie de `main` à jour ; pas de PR empilées.
- Messages au format Conventional Commits, en français (`type(portée): description`).
- Merge par merge commit (le commit de formatage est référencé dans `.git-blame-ignore-revs`).

### Migrations de données

- Une migration de données n'importe pas le code de l'application (les modèles et le parseur évoluent) : elle utilise `apps.get_model` et, si besoin, une copie figée des fonctions utiles.
- Elle échoue sans rien modifier si les données ne sont pas dans l'état attendu, plutôt que de perdre de l'information.
- Avant la PR, elle est vérifiée sur une **copie** de la base réelle (comparaison avant / après, en SQL).
- Avant de l'appliquer : sauvegarder `db.sqlite3`.
