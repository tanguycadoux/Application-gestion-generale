# Application de gestion générale

Application pour l'organisation quotidienne.

Projet Django `app_gestion`, contenant des applications :

- `note_taking` pour la prise de notes,
- `todolist` pour la gestion de TODO.

## Installation et lancement

Prérequis : Python 3.14 ou supérieur.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py tailwind runserver
```

L'application est ensuite accessible sur <http://127.0.0.1:8000/>.

`tailwind runserver` lance le serveur Django et reconstruit la feuille de style Tailwind à chaque modification d'un gabarit ou d'un script. Au premier lancement, il télécharge le CLI de Tailwind (environ 110 Mo, sans Node) dans `.django_tailwind_cli/` : c'est une étape d'installation, l'application elle-même ne fait aucune requête vers l'extérieur. La feuille compilée (`static/css/tailwind.css`) n'est pas versionnée ; pour la construire une seule fois, sans serveur : `python manage.py tailwind build`.

### Dépendances

Les dépendances sont maintenues à la main, avec des versions épinglées :

- `requirements.txt` : dépendances d'exécution,
  - `Django`,
  - `Markdown` pour le rendu HTML des notes,
  - `django-htmx` pour les mises à jour partielles de pages (recherche de notes),
  - `django-tailwind-cli` pour compiler la feuille Tailwind (CLI autonome de Tailwind, sans Node),
  - `Pillow` pour le stockage des images de notes (`ImageField`) ;
- `requirements-dev.txt` : dépendances d'exécution et outillage de développement (`mypy`, `django-stubs`, `ruff`).

Pour ajouter ou mettre à jour une dépendance, l'installer dans le venv puis reporter la version installée (`pip list`) dans le fichier concerné.

### Front

HTML, CSS et JavaScript natifs, sans Node. Seule étape de build : la feuille Tailwind, compilée par `django-tailwind-cli` (voir « Installation et lancement »). Les notes étant privées, l'application ne charge aucune ressource depuis Internet : tout est servi en local (#217).

| Outil | Rôle | Chargement |
|---|---|---|
| [Tailwind CSS](https://tailwindcss.com/) | style de l'interface (classes utilitaires) | version 4.3.3 (`TAILWIND_CLI_VERSION`), compilée dans `static/css/tailwind.css` (non versionnée) et chargée par `{% tailwind_css %}` dans `core/templates/base.html` ; thème, styles de base et animations des alertes dans la source `assets/css/source.css` |
| [Material Symbols Rounded](https://fonts.google.com/icons) | icônes (Material 3, variante arrondie) | Google Fonts, dans `core/templates/base.html` ; usage : `<span class="material-symbols-rounded">edit</span>` (passage en SVG local : #218) |
| [htmx](https://htmx.org/) | mises à jour partielles de pages (recherche de notes, navigation des calendriers) | version 1.9.11, embarquée dans `static/vendor/htmx/` (licence, provenance et empreinte dans son README), chargée une fois dans `core/templates/base.html` |

Tailwind détecte les classes dans les fichiers du dépôt (gabarits, code Python, scripts), hors fichiers ignorés par git : une classe n'est générée que si elle est écrite quelque part en entier.

Règle de style : tout le style est en classes Tailwind (#79), dans les gabarits, les composants ou les scripts qui créent des éléments. Il ne reste que deux ensembles de règles CSS propres, pour ce que Tailwind ne couvre pas : `note_taking/static/note_taking/style.css` (HTML produit par le Markdown des notes, sur lequel on ne peut pas mettre de classes : listes, titres, tableaux, callouts) et le bloc `@layer components` de `assets/css/source.css` (animations des alertes créées en JavaScript, dont l'apparence est en classes Tailwind dans `alert_system.js`, #154), rangé dans ce layer pour que les classes Tailwind puissent le surcharger. Une nouvelle feuille CSS ne se justifie que dans un cas semblable ; une feuille hors `@layer` l'emporte sur toutes les classes Tailwind. Les classes Tailwind sont écrites en entier, sans les construire par morceaux, pour que la compilation les trouve.

Couleurs (#128) : uniquement celles de Tailwind, une famille par rôle : `slate` pour les gris, `blue` pour la couleur principale, `red` pour le danger et les erreurs, `amber` pour les avertissements, `green` pour les succès, plus `white` et `black`. Pas de couleur en dur, ni en classe arbitraire (`bg-[oklch(…)]`), ni dans les feuilles CSS propres, qui utilisent les variables de Tailwind (`var(--color-slate-200)`). Ces variables existent toutes grâce à `@import "tailwindcss" theme(static)` dans `assets/css/source.css`. Seules exceptions : les couleurs des callouts reprises de Quarto (`note_taking/static/note_taking/style.css`), et les ombres et voiles noirs transparents. `core/tests/test_colors.py` vérifie la règle.

Couleurs des projets (#162) : chaque projet a une famille parmi `orange`, `yellow`, `lime`, `emerald`, `teal`, `cyan`, `sky`, `indigo`, `violet`, `purple`, `fuchsia`, `pink`, `rose`, c'est-à-dire hors gris et hors familles qui ont un rôle, pour qu'un projet ne se confonde pas avec un état. Elles sont réservées aux projets : seule la pastille (`{% project_badge %}`, `core/templatetags/ui.py`) les emploie. Un projet créé sans couleur, par l'import d'une note ou d'une tâche, reçoit la famille la moins utilisée. La page « Projets » (`/projets/`, liée depuis l'accueil général) permet de créer un projet, d'en modifier la couleur et la description, et de le supprimer s'il n'est utilisé par aucune note ni tâche.

Liens (#127) : un style de base pour tout lien sans classe (`a:not([class])`, bloc `@layer base` de `assets/css/source.css`), y compris dans le contenu des notes : `blue-700` souligné, plus foncé avec un soulignement épaissi au survol, contour visible au focus clavier. Un lien de texte s'écrit donc sans classe ; un lien qui a sa propre apparence (bouton, menu, case du calendrier) porte ses classes et n'est pas concerné.

Formulaires (#132) : les champs ont un style de base (`@layer base` de `assets/css/source.css`) : largeur bornée à leur conteneur (`max-w-full`, sans quoi une longue option de `<select>` élargit la page), bordure `slate-300`, contour `blue-700` au focus, bordure rouge si `aria-invalid="true"` (posé par Django sur un champ en erreur), erreurs `.errorlist` en `red-800`, cases en `blue-700`, bouton « Parcourir » des champs fichier à l'image d'un bouton `ghost`. Un formulaire à plusieurs champs est une grille, libellés à gauche : le `<form>` porte `grid grid-cols-[max-content_1fr] items-baseline gap-x-3 gap-y-3`, `{{ form }}` y rend deux cellules par champ (`core/templates/core/forms/grid.html`, via `FORM_RENDERER`). Le bouton d'envoi n'est pas dans la grille : il est en haut à droite, dans l'en-tête de la page, en `ghost` à icône seule comme la barre d'outils d'une note, et envoie le formulaire par son identifiant (`{% button "Enregistrer la note" icon="save" variant="ghost" icon_only=True form="note-form" %}`). Un formulaire à un seul champ garde libellé et champ sur une ligne.

Dates (#129) : trois formats d'affichage, selon l'usage, définis dans `core/templatetags/ui.py` (`DATE_FORMATS`) : **long** « lundi 24 novembre 2025 » quand la date nomme une note (titres, liens « Note du … »), **moyen** « 24 novembre 2025 » dans un texte ou une fiche (échéance, dates d'une image, messages), **court** « lun. 24 nov. 2025 » dans les tableaux et les listes. Dans une page, `{% date_time valeur "long" %}` produit `<time datetime="2025-11-24">lundi 24 novembre 2025</time>` ; dans un attribut ou un message, le filtre `{{ valeur|date_text:"moyen" }}`. Le filtre `date` de Django ne sert plus qu'aux formats techniques (`Y-m-d`, `c`, `Y-m`) et au mois du calendrier (`F Y`).

Titres et vocabulaire (#130) : le titre d'onglet suit le modèle « Page · Section » (« Liste des notes · Notes », « Tâche « Relire » · Tâches ») ; une page définit `{% block title %}`, le gabarit de base de son application ajoute la section (`{% block title_suffix %}`), et l'accueil général s'appelle « Gestion générale ». Une date dans un titre d'onglet est au format moyen. Un élément de la liste de l'app des TODO est une **tâche** (« Créer une tâche », « sous-tâche ») ; le marqueur TODO écrit dans les notes garde son nom.

Composants partagés, à charger avec `{% load ui %}` (balises dans `core/templatetags/ui.py`, gabarits dans `core/templates/core/components/`) :

| Balise | Rendu |
|---|---|
| `{% nav_link "app:vue" "Libellé" "icône" %}` | lien du menu, marqué actif (`aria-current="page"`) sur sa page |
| `{% button "Libellé" href=url icon="…" variant="…" type="submit" icon_only=True disabled=True form="id" describedby="id" %}` | bouton : `<a>` si `href` est fourni, sinon `<button type="…">` ; variantes `primary` (par défaut), `danger`, `ghost` (fond transparent) et `ghost-danger` (voir la règle d'usage ci-dessous) ; avec `icon_only`, le libellé passe en `aria-label` ; `disabled` désactive un `<button>` (pas un lien) ; `form="id"` relie un `<button>` placé hors de son formulaire (pas un lien) ; `describedby="id"` pose `aria-describedby`, par exemple vers la raison pour laquelle le bouton est désactivé |
| `{% tag_list tags %}` | liste de tags en pastilles, rien si elle est vide |
| `{% project_badge projet %}` | pastille d'un projet : un point de sa couleur devant son nom, rien sans projet |

Exemples :

```django
{% load ui %}
{% button "Importer" %}
{% url 'todolist:todo_edit' todo.pk as url %}{% button "Modifier" href=url %}
{% button "Supprimer la note" icon="delete" href=url variant="ghost-danger" icon_only=True %}
```

Usage des variantes de bouton (#145) : un bouton **plein** (`primary`, `danger`) pour l'action principale d'une page ou d'une zone, en général une seule (Importer, Ouvrir la note du jour…) ; un bouton **`ghost`** pour la barre d'outils à côté du titre : actions sur l'objet affiché (exporter, modifier, et supprimer en `ghost-danger`) et enregistrement d'un formulaire ; et pour la navigation (mois précédent/suivant, retour). Toutes les variantes ont la même forme, sans marge : l'espacement revient au conteneur. Au survol, le fond d'un bouton plein s'éclaircit ; un `ghost`, sans fond, en prend un. Les suppressions (`danger`, `ghost-danger`) ont le texte en rouge.

Icônes des boutons (#131) : tout bouton a une icône (paramètre `icon`, jamais un caractère dans le libellé comme « + »), une par action, la même partout (`core/tests/test_icons.py` le vérifie) :

| Action | Icône |
|---|---|
| créer, ajouter | `add` |
| modifier | `edit` |
| supprimer | `delete` |
| enregistrer | `save` |
| exporter | `download` |
| importer | `upload` |
| retour | `arrow_back` |
| mois précédent, suivant | `chevron_left`, `chevron_right` |
| aujourd'hui, note du jour | `today` |

Confirmation avant envoi : un formulaire qui porte `data-confirm="message"` ouvre une popover de confirmation (`Alert.confirmAt`) à côté de son bouton d'envoi, avec « Annuler » en `ghost` puis « Supprimer » en `danger` (`core/static/core/confirm.js`, chargé par le gabarit de base) ; sans JavaScript, il s'envoie directement. Toute suppression passe par là (#126) : un bouton `ghost-danger` dans un formulaire POST portant `data-confirm`, vers une vue limitée à POST ; il n'y a pas de page de confirmation.

Les principes de ces composants (un composant par rôle, l'apparence en variante, des paramètres ajoutés seulement quand une page en a besoin) sont décrits dans `docs/architecture.md`, section « Composants d'interface ».


Le type checking se fait avec `mypy` et `django-stubs` (configuration dans `mypy.ini`) :

```powershell
mypy .
```

Le lint et le formatage se font avec `ruff` (configuration dans `pyproject.toml`) :

```powershell
ruff check .        # lint (ajouter --fix pour corriger automatiquement)
ruff format .       # formatage
```

Les tests se lancent avec :

```powershell
python manage.py test
```

Le parseur de notes est testé sur une note d'exemple (`note_taking/tests/data/exemple.qmd`) dont le résultat attendu est figé dans `exemple.json`. Après un changement de comportement voulu, régénérer ce fichier puis relire son diff :

```powershell
$env:UPDATE_GOLDEN = "1"; python manage.py test note_taking.tests.test_parser; Remove-Item Env:UPDATE_GOLDEN
```

Les commits de formatage pur sont listés dans `.git-blame-ignore-revs`. Pour que `git blame` les ignore :

```powershell
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

### Structure du dépôt

```
app_gestion/          # configuration du projet (settings, urls)
core/                 # éléments communs : projets, sujets, tags, page d'accueil, gabarit de base, statiques
images/               # images utilisables dans les notes (modèle, import)
note_taking/          # application de prise de notes
todolist/             # application de gestion des TODO
docs/                 # documentation (architecture et décisions)
assets/css/source.css # source de la feuille Tailwind (thème, styles de base)
static/               # statiques communs : bibliothèques embarquées (vendor/), feuille compilée (css/, non versionnée)
manage.py
db.sqlite3            # base de données (non versionnée)
media/note_images/    # images importées (non versionnées)
notes_quarto_files/   # fichiers sources .qmd des notes (non versionnés)
```

## Prise de notes

Les notes sont organisées par jour : une note correspond à une date (unique) et son contenu est stocké en base de données (champ `body`), au format markdown / quarto. La base fait foi : le corps est stocké sans bloc d'en-tête (`---` / `date: …` / `---`), la date étant celle de la note.

Une note peut être :

- créée et modifiée directement dans l'application (`/note_taking/note/new/`, puis `/note_taking/note/<id>/edit/`),
- importée depuis un ou plusieurs fichiers quarto (`.qmd`),
- mise à jour depuis un fichier source, depuis sa vue détail.

À chaque enregistrement, le contenu est analysé et découpé en *note parts* (voir ci-dessous), et les TODO éventuelles sont générées.

### Import de fichiers

Le nom du fichier doit être la date de la note au format `AAAA-MM-JJ` (exemple : `2025-11-24.qmd`).

Le fichier doit commencer par un bloc de métadonnées dont la date correspond au nom du fichier :

```
---
date: 2025-11-24
---
```

Ce bloc sert uniquement à vérifier la date : il est retiré avant l'enregistrement. Dans l'éditeur de l'application, un bloc d'en-tête éventuel est traité de la même manière (une date différente de celle de la note est refusée).

### Structure générale

Une note est structurée de cette manière :

```
# Projet (exemple : ASTERICS)
## Sujet (exemple : Caractérisation mécanique)
### Tag 1 (exemple : Mesure géométrique des pièces et échantillons)
#### Tag 2
##### Tag 3
###### Tag 4
```

Les titres sont cumulatifs, ce qui signifie qu'un texte contenu sous "Tag 2" hérite du projet, sujet et Tag 1. Par convention, même si un titre contient une virgule, il est considéré comme un tag à part entière (par exemple le titre "Conception, approvisionnement et fabrication" donnera le tag `Conception, approvisionnement et fabrication` et non les tags `Conception` et `approvisionnement et fabrication`).

Le contenu est découpé en *note parts* : chaque note part regroupe le texte partageant le même projet, le même sujet et les mêmes tags. Les projets sont créés automatiquement s'ils n'existent pas encore. Projets, sujets et tags sont communs aux notes et aux TODO (app `core`). Un projet utilisé par une note ou une TODO ne peut pas être supprimé. Un sujet est indépendant des projets (le même sujet peut apparaître dans plusieurs projets) ; un sujet ou un tag qui n'est plus utilisé reste en base mais n'est plus proposé dans la recherche.

Les titres présents dans les blocs de code (` ``` `) et dans les callouts (`::: {.callout-note ...}`) ne sont pas interprétés.

### Tags supplémentaires

Il est possible d'ajouter plus de tags en ajoutant un bloc avec la classe `metadata` :

```
::: {.metadata}
tags: [tag supplémentaire 1, tag supplémentaire 2]
:::
```

Lorsque des tags sont spécifiés de cette manière, ils ajoutent les tags à ceux déjà présents précédemment, et sont conservés dans les titres de niveau plus profonds. Si au même niveau un autre jeu de tags est donné, il remplace le précédent :

```
# Projet
## Sujet
### Tag 1

Tags : Tag 1

::: {.metadata}
tags: [m1, m2]
:::

Tags : Tag 1, m1, m2

::: {.metadata}
tags: [m3, m4]
:::

Tags : Tag 1, m3, m4

#### Tag 2
##### Tag 3

Tags : Tag 1, m3, m4, Tag 2, Tag 3

::: {.metadata}
tags: [m5, m6]
:::

Tags : Tag 1, m3, m4, Tag 2, Tag 3, m5, m6

###### Tag 4

Tags : Tag 1, m3, m4, Tag 2, Tag 3, m5, m6, Tag 4
```

### Génération des TODO

Toute note part portant le tag `TODO` (par exemple via un titre `### TODO`) génère une TODO par ligne de contenu dans l'application `todolist` :

```
# Projet
## Sujet
### TODO

- Première tâche
- Deuxième tâche
```

Le titre de la TODO est le texte de la ligne, sans son marqueur de liste (`-`, `*`, `+`, `1.`, `1)`) ni sa case (`[ ]`, `[x]`) : une case cochée ne crée pas de tâche terminée (#222). Une ligne vide ou réduite à son marqueur est ignorée ; le titre est limité à 500 caractères.

Chaque TODO est rattachée au projet et au sujet de la note part, a pour échéance la date de la note et reçoit comme tags ceux de la note part (sans `TODO`). Une TODO déjà générée pour la même date et le même texte n'est pas recréée.

### Images

Les images sont importées séparément (bouton d'import, liste sur `/note_taking/images/`) et stockées dans `media/note_images/`. Dans une note, une image est référencée par son nom de fichier :

```
![Légende](chemin/vers/image.png)
```

Au moment de l'analyse, le chemin est remplacé par une référence vers l'image en base (`image:<id>`), à partir du nom de fichier uniquement. L'image doit donc avoir été importée avant la note.

Une image désignée par une adresse externe (`![Légende](https://…)`) n'est pas une image importée : elle ne bloque pas l'analyse, et elle n'est pas chargée. Elle s'affiche comme un lien vers son adresse, avec sa légende pour texte, pour que le navigateur ne contacte aucun serveur tiers (#220).

Les images sont gérées par l'app `images` (modèle `Image`) ; leurs pages restent dans la prise de notes. Une image a un nom (son nom de fichier d'origine, unique), un fichier affiché et, pour les images créées dans l'application à terme, un fichier source éditable. Son format (vectoriel ou matriciel) se déduit du fichier, et son origine (importée ou créée dans l'application) de la présence d'une source.

Chaque note part est liée aux images qu'elle utilise (liens recalculés à chaque enregistrement de la note). Une image utilisée par une note ne peut pas être supprimée.

### Fonctionnalités

- liste des notes, triable par colonne (`/note_taking/notes/`),
- vue détail d'une note, rendu markdown complet (`/note_taking/note/<id>/md/`) et résultat de l'analyse en JSON (`/note_taking/note/<id>/json/`),
- recherche des note parts par projet(s) et sujet(s) (`/note_taking/notes/search/`), les sujets proposés étant filtrés selon les projets cochés,
- suppression d'une note.

## Gestion des tâches

Les tâches peuvent être créées manuellement ou générées depuis les notes (lignes d'une section marquée du tag TODO). Une tâche possède :

- un titre et une description,
- un projet (obligatoire), un sujet facultatif et des tags ; une tâche issue d'une note reprend le projet, le sujet et les tags de sa note part,
- une priorité (basse, moyenne, haute),
- une date d'échéance facultative,
- un avancement de 0 à 100 %,
- un état « terminée »,
- une tâche parente éventuelle (sous-tâches).

Une tâche sans sous-tâche est terminée à 100 % d'avancement. Une tâche qui a des sous-tâches a un avancement **calculé** : la moyenne de celui de ses enfants, recalculée à chaque changement d'un enfant, sur tous les niveaux (#164) ; il ne se saisit pas. Elle se **valide à la main** : la cocher la marque terminée, à tout moment (une validation alors que des enfants sont en cours est une incohérence, signalée). Tant qu'elle n'est pas cochée, elle reste en cours, « à valider » quand tous ses enfants sont terminés ; et elle se décoche d'elle-même dès qu'un de ses enfants n'est plus terminé. Le formulaire d'une sous-tâche propose le projet et l'échéance de sa parente, sans les imposer. Seule une boucle parent-enfant est refusée.

Le détail d'une tâche qui a des sous-tâches montre, sous leur tableau, une **frise de type Gantt** (#168, `todolist/gantt.py`, `todolist/gantt.html`) : la tâche observée en première ligne, puis une ligne par sous-tâche, indentée comme dans le tableau ; une barre de sa création à son échéance (jusqu'à aujourd'hui, bord droit en pointillés, si elle n'en a pas), remplie selon son avancement, aux couleurs du signal de son échéance ; un trait pour aujourd'hui et un trait pointillé pour l'échéance de la tâche ; un repère au début de chaque mois. Les positions, en pourcentage de l'axe, passent par des variables CSS lues par des classes Tailwind (`left-(--start)`), sans localisation (`unlocalize`).

L'accueil des tâches est un calendrier du mois (#167), sur le même composant que celui des notes (`core/month_calendar.py`, `core/components/month_calendar.html` ; chaque app fournit le gabarit d'une case) : une tâche en cours s'y place à son échéance, une tâche terminée à sa date de complétion (`completed_at`, remplie quand elle passe à terminée, vidée sinon) ; trois tâches au plus par case (point du projet, titre en lien, terminées atténuées, en retard en rouge), puis « + N autres » ; un « + » au survol crée une tâche avec cette échéance.

Les écarts entre une tâche et ses sous-tâches ne sont pas empêchés mais **signalés** (#165), sur le parent comme sur l'enfant : échéance d'une sous-tâche après celle de son parent, projet différent de celui du parent, parent terminé avec une sous-tâche en cours. Le détail d'une tâche les liste dans un encadré « À corriger », avec un lien vers l'autre tâche ; les listes marquent une tâche incohérente d'une icône d'avertissement.

La liste (`/todolist/todos`) est un tableau arborescent (#166) : chaque tâche racine forme un groupe, ouvert par la pastille de son projet, avec ses sous-tâches indentées sous leur parent direct. Une ligne porte la case à cocher, le nom (lien vers le détail, avec la mention « à valider » d'un parent et l'icône d'incohérence), l'avancement en barre (`<progress>`, bleue en cours, verte à 100 %, #182), le temps restant (« aujourd'hui », « dans 3 j », « 2 j de retard », en semaines puis en mois au-delà de 30 et 90 jours ; rouge en retard, ambre sous 3 jours) et l'échéance. Les frères sont triés par échéance, sans échéance à la fin, et les racines par l'échéance la plus proche des tâches non terminées de leur arbre. Les arbres dont la racine est terminée sont dans une section repliée. Le détail d'un parent reprend le même tableau pour ses sous-tâches (`todolist/task_table.html`, arbre construit par `todolist/tree.py`). La case d'une tâche sans sous-tâche la passe à 100 % ou à 0 % ; celle d'une tâche qui a des sous-tâches la valide ou non.

## Orientations

Le suivi détaillé se fait dans les [issues](https://github.com/tanguycadoux/Application-gestion-generale/issues) et les [milestones](https://github.com/tanguycadoux/Application-gestion-generale/milestones) GitHub. Cette section ne donne que les grandes lignes.

Principes :

- application locale et mono-utilisateur ; aucune donnée des notes ne quitte la machine (l'assistant et l'OCR passent par des services locaux) ;
- la base de données fait foi, le format qmd sert à l'import et à l'export ;
- front sans Node : HTML, CSS et JS natifs (htmx pour les mises à jour partielles), feuille Tailwind compilée par son CLI autonome ; aucune ressource chargée depuis Internet.

La réorganisation du code (milestones M1 à M3 : tests et outillage, nettoyage, restructuration des apps et du modèle de données) est terminée. L'organisation du code, les décisions structurantes et les conventions de travail sont décrites dans [`docs/architecture.md`](docs/architecture.md).

Milestones terminés :

| Milestone | Contenu |
|---|---|
| M4 · Fondations de l'interface | style Tailwind et icônes Material, composants réutilisables, corrections de rendu |
| M5 · Navigation dans les notes | accès direct à la note du jour, vue calendrier |
| M6 · Images | page détail d'une image avec les notes liées, suppression des images inutilisées |
| M7 · Export et import qmd | export des notes et de leurs images en archive zip, import unifié (notes, images, archives) |
| M8 · Cohérence de l'interface | couleurs Tailwind, styles communs des liens, boutons, formulaires et alertes, suppression par popover, formats de date, titres d'onglet et vocabulaire, icônes ; règles décrites dans la section Front |
| M9 · Interface des tâches | page Projets et couleur par projet, modèle des tâches (sujet, avancement, validation d'un parent), incohérences signalées, tableau arborescent avec barre d'avancement, calendrier partagé avec les notes, frise de type Gantt |

Évolutions planifiées, dans l'ordre :

| Milestone | Contenu |
|---|---|
| M10 · Qualité du code | dépendances entre apps sans cycle, front sans ressource externe (Tailwind compilé, htmx et icônes en local), performances des listes, règles et messages cohérents, accessibilité, documentation d'architecture à jour |
| M11 · Rendu fidèle à Quarto | sous-listes, légendes de tableau, cases à cocher et formules affichées comme dans Quarto |
| M12 · Tâches issues des notes | sous-listes en sous-tâches, pas d'échéance par défaut, page bilan des tâches créées, tâches supprimées qui ne reviennent pas, avancement rendu au décochage |
| M13 · Éditeur de notes assisté | insertion des titres de projet et de sujet et des images depuis des listes, collage de captures d'écran |
| M14 · Éditeur d'images | création et modification d'images vectorielles et matricielles, renommage d'une image dans les notes |
| M15 · Navigation et affichage des notes | menu commun repliable, accueil en tableau de bord, note affichée telle qu'écrite, section de debug, URL en anglais |
| M16 · Recherche plein texte | recherche dans le corps des notes, syntaxe `project:`, `tag:`, `"phrase exacte"`, tolérance aux fautes, résultats groupés par note, palette Ctrl+K, recherches enregistrées, texte des images |
| M17 · Projets et liens entre notes | fiche projet, renommage d'un projet, liens entre notes compatibles Quarto, bilan de la semaine |
| M18 · Assistant local | IA optionnelle et 100 % locale : résumé d'un projet, questions sur les notes, correction orthographique, tâches suggérées |
