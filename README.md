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
python manage.py runserver
```

L'application est ensuite accessible sur <http://127.0.0.1:8000/>.

### Dépendances

Les dépendances sont maintenues à la main, avec des versions épinglées :

- `requirements.txt` : dépendances d'exécution,
  - `Django`,
  - `Markdown` pour le rendu HTML des notes,
  - `django-htmx` pour les mises à jour partielles de pages (recherche de notes),
  - `Pillow` pour le stockage des images de notes (`ImageField`) ;
- `requirements-dev.txt` : dépendances d'exécution et outillage de développement (`mypy`, `django-stubs`, `ruff`).

Pour ajouter ou mettre à jour une dépendance, l'installer dans le venv puis reporter la version installée (`pip list`) dans le fichier concerné.

### Front

Pas d'étape de build : HTML, CSS et JavaScript natifs, bibliothèques chargées depuis un CDN.

| Outil | Rôle | Chargement |
|---|---|---|
| [Tailwind CSS](https://tailwindcss.com/) | style de l'interface (classes utilitaires) | version 4.3.3, `@tailwindcss/browser` sur jsDelivr, dans `core/templates/base.html` ; thème et styles de base dans le bloc `<style type="text/tailwindcss">` du même gabarit |
| [Material Symbols Rounded](https://fonts.google.com/icons) | icônes (Material 3, variante arrondie) | Google Fonts, dans `core/templates/base.html` ; usage : `<span class="material-symbols-rounded">edit</span>` |
| [htmx](https://htmx.org/) | mises à jour partielles de pages (recherche de notes) | unpkg, version 1.9.11, dans `note_taking/templates/note_taking/base.html` |

Règle de style : tout le style est en classes Tailwind (#79), dans les gabarits, les composants ou les scripts qui créent des éléments. Il ne reste que deux feuilles CSS propres, pour ce que Tailwind ne couvre pas : `note_taking/static/note_taking/style.css` (HTML produit par le Markdown des notes, sur lequel on ne peut pas mettre de classes : listes, titres, tableaux, callouts) et `core/static/core/alert_system.css` (alertes créées en JavaScript, avec leurs animations), rangée dans `@layer components` pour que les classes Tailwind puissent la surcharger. Une nouvelle feuille CSS ne se justifie que dans un cas semblable ; une feuille hors `@layer` l'emporte sur toutes les classes Tailwind. Les classes Tailwind sont écrites en entier, sans les construire par morceaux, pour rester compatibles avec une future étape de build.

Couleurs (#128) : uniquement celles de Tailwind, une famille par rôle : `slate` pour les gris, `blue` pour la couleur principale, `red` pour le danger et les erreurs, `amber` pour les avertissements, `green` pour les succès, plus `white` et `black`. Pas de couleur en dur, ni en classe arbitraire (`bg-[oklch(…)]`), ni dans les feuilles CSS propres, qui utilisent les variables de Tailwind (`var(--color-slate-200)`). Ces variables existent toutes grâce à `@import "tailwindcss" theme(static)` dans `core/templates/base.html`. Seules exceptions : les couleurs des callouts reprises de Quarto (`note_taking/static/note_taking/style.css`), et les ombres et voiles noirs transparents. `core/tests/test_colors.py` vérifie la règle.

Liens (#127) : un style de base pour tout lien sans classe (`a:not([class])`, bloc `@layer base` de `core/templates/base.html`), y compris dans le contenu des notes : `blue-700` souligné, plus foncé avec un soulignement épaissi au survol, contour visible au focus clavier. Un lien de texte s'écrit donc sans classe ; un lien qui a sa propre apparence (bouton, menu, case du calendrier) porte ses classes et n'est pas concerné.

Formulaires (#132) : les champs ont un style de base (`@layer base` de `core/templates/base.html`) : largeur bornée à leur conteneur (`max-w-full`, sans quoi une longue option de `<select>` élargit la page), bordure `slate-300`, contour `blue-700` au focus, bordure rouge si `aria-invalid="true"` (posé par Django sur un champ en erreur), erreurs `.errorlist` en `red-800`, cases en `blue-700`, bouton « Parcourir » des champs fichier à l'image d'un bouton `ghost`. Un formulaire à plusieurs champs est une grille, libellés à gauche : le `<form>` porte `grid grid-cols-[max-content_1fr] items-baseline gap-x-3 gap-y-3`, `{{ form }}` y rend deux cellules par champ (`core/templates/core/forms/grid.html`, via `FORM_RENDERER`), et le bouton d'envoi se place dans la colonne des champs (`<div class="col-start-2">`). Un formulaire à un seul champ garde libellé et champ sur une ligne.

Composants partagés, à charger avec `{% load ui %}` (balises dans `core/templatetags/ui.py`, gabarits dans `core/templates/core/components/`) :

| Balise | Rendu |
|---|---|
| `{% nav_link "app:vue" "Libellé" "icône" %}` | lien du menu, marqué actif (`aria-current="page"`) sur sa page |
| `{% button "Libellé" href=url icon="…" variant="…" type="submit" icon_only=True disabled=True %}` | bouton : `<a>` si `href` est fourni, sinon `<button type="…">` ; variantes `primary` (par défaut), `danger`, `ghost` (fond transparent) et `ghost-danger` (voir la règle d'usage ci-dessous) ; avec `icon_only`, le libellé passe en `aria-label` ; `disabled` désactive un `<button>` (pas un lien) |
| `{% tag_list tags %}` | liste de tags en pastilles, rien si elle est vide |

Exemples :

```django
{% load ui %}
{% button "Importer" %}
{% url 'todolist:todo_edit' todo.pk as url %}{% button "Modifier" href=url %}
{% button "Supprimer la note" icon="delete" href=url variant="ghost-danger" icon_only=True %}
```

Usage des variantes de bouton (#145) : un bouton **plein** (`primary`, `danger`) pour l'action principale d'une page ou d'une zone, en général une seule (Enregistrer, Importer, Ouvrir la note du jour…) ; un bouton **`ghost`** pour les actions sur l'objet affiché, en barre d'outils à côté du titre (exporter, modifier, et supprimer en `ghost-danger`), et pour la navigation (mois précédent/suivant, retour). Toutes les variantes ont la même forme, sans marge : l'espacement revient au conteneur. Au survol, le fond d'un bouton plein s'éclaircit ; un `ghost`, sans fond, en prend un. Les suppressions (`danger`, `ghost-danger`) ont le texte en rouge.

Confirmation avant envoi : un formulaire qui porte `data-confirm="message"` ouvre une popover de confirmation (`Alert.confirmAt`) à côté de son bouton d'envoi (`core/static/core/confirm.js`, chargé par le gabarit de base) ; sans JavaScript, il s'envoie directement.

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

Chaque TODO est rattachée au projet, a pour échéance la date de la note et reçoit comme tags ceux de la note part (sans `TODO`) ainsi que le sujet. Une TODO déjà générée pour la même date et le même texte n'est pas recréée.

### Images

Les images sont importées séparément (bouton d'import, liste sur `/note_taking/images/`) et stockées dans `media/note_images/`. Dans une note, une image est référencée par son nom de fichier :

```
![Légende](chemin/vers/image.png)
```

Au moment de l'analyse, le chemin est remplacé par une référence vers l'image en base (`image:<id>`), à partir du nom de fichier uniquement. L'image doit donc avoir été importée avant la note.

Les images sont gérées par l'app `images` (modèle `Image`) ; leurs pages restent dans la prise de notes. Une image a un nom (son nom de fichier d'origine, unique), un fichier affiché et, pour les images créées dans l'application à terme, un fichier source éditable. Son format (vectoriel ou matriciel) se déduit du fichier, et son origine (importée ou créée dans l'application) de la présence d'une source.

Chaque note part est liée aux images qu'elle utilise (liens recalculés à chaque enregistrement de la note). Une image utilisée par une note ne peut pas être supprimée.

### Fonctionnalités

- liste des notes, triable par colonne (`/note_taking/notes/`),
- vue détail d'une note, rendu markdown complet (`/note_taking/note/<id>/md/`) et résultat de l'analyse en JSON (`/note_taking/note/<id>/json/`),
- recherche des note parts par projet(s) et sujet(s) (`/note_taking/notes/search/`), les sujets proposés étant filtrés selon les projets cochés,
- suppression d'une note.

## Gestion des TODO

Les TODO peuvent être créées manuellement ou générées depuis les notes. Une TODO possède :

- un titre et une description,
- un projet et des tags,
- une priorité (basse, moyenne, haute),
- une date d'échéance,
- une TODO parente éventuelle (sous-tâches).

Une sous-tâche hérite du projet de sa parente, ainsi que de son échéance si elle n'en a pas.

La liste (`/todolist/todos`) sépare les TODO en cours des TODO terminées et les trie par échéance, en prenant en compte l'échéance la plus proche des sous-tâches non terminées. L'affichage dépend de l'échéance : dépassée, pour aujourd'hui, prochainement (sous 3 jours).

Valider une TODO valide aussi ses sous-tâches, après confirmation si certaines ne sont pas terminées.

## Orientations

Le suivi détaillé se fait dans les [issues](https://github.com/tanguycadoux/Application-gestion-generale/issues) et les [milestones](https://github.com/tanguycadoux/Application-gestion-generale/milestones) GitHub. Cette section ne donne que les grandes lignes.

Principes :

- application locale et mono-utilisateur ;
- la base de données fait foi, le format qmd sert à l'import et à l'export ;
- front sans étape de build : HTML, CSS et JS natifs (htmx pour les mises à jour partielles).

La réorganisation du code (milestones M1 à M3 : tests et outillage, nettoyage, restructuration des apps et du modèle de données) est terminée. L'organisation du code, les décisions structurantes et les conventions de travail sont décrites dans [`docs/architecture.md`](docs/architecture.md).

Milestones terminés :

| Milestone | Contenu |
|---|---|
| M4 · Fondations de l'interface | style Tailwind et icônes Material, composants réutilisables, corrections de rendu |
| M5 · Navigation dans les notes | accès direct à la note du jour, vue calendrier |
| M6 · Images | page détail d'une image avec les notes liées, suppression des images inutilisées |
| M7 · Export et import qmd | export des notes et de leurs images en archive zip, import unifié (notes, images, archives) |

Évolutions planifiées, dans l'ordre :

| Milestone | Contenu |
|---|---|
| M8 · Cohérence de l'interface | défauts et incohérences relevés à la revue de l'interface : en-tête HTML, messages, formulaires, suppression, liens, couleurs, dates, vocabulaire, icônes |
| M9 · Interface des TODO | refonte de l'affichage des TODO sur les composants et les couleurs de l'application |
| M10 · Éditeur de notes assisté | insertion des titres de projet et de sujet et des images depuis des listes |
| M11 · Éditeur d'images | création et modification d'images vectorielles et matricielles |
