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

Côté front, Tailwind et htmx sont chargés depuis un CDN.

Le type checking se fait avec `mypy` et `django-stubs` (configuration dans `mypy.ini`) :

```powershell
mypy .
```

### Structure du dépôt

```
app_gestion/          # configuration du projet (settings, urls, templates et statiques communs)
note_taking/          # application de prise de notes
todolist/             # application de gestion des TODO
manage.py
db.sqlite3            # base de données (non versionnée)
media/note_images/    # images importées (non versionnées)
notes_quarto_files/   # fichiers sources .qmd des notes (non versionnés)
```

## Prise de notes

Les notes sont organisées par jour : une note correspond à une date (unique) et son contenu est stocké en base de données (champ `raw`), au format markdown / quarto.

Une note peut être :

- créée et modifiée directement dans l'application (`/note_taking/note/new/`, puis `/note_taking/note/<id>/edit/`),
- importée depuis un ou plusieurs fichiers quarto (`.qmd`),
- mise à jour depuis un fichier source, depuis sa vue détail.

À chaque enregistrement, le contenu est analysé et découpé en *note parts* (voir ci-dessous), et les TODO éventuelles sont générées.

### Import de fichiers

Le nom du fichier doit être la date de la note au format `AAAA-MM-JJ` (exemple : `2025-11-24.qmd`). Un fichier préfixé par `TEST_` (exemple : `TEST_2025-11-24.qmd`) est marqué comme note de test.

Le fichier doit commencer par un bloc de métadonnées dont la date correspond au nom du fichier :

```
---
date: 2025-11-24
---
```

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

Le contenu est découpé en *note parts* : chaque note part regroupe le texte partageant le même projet, le même sujet et les mêmes tags. Les projets sont créés automatiquement s'ils n'existent pas encore.

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

En cours : réorganisation du code pour préparer les évolutions (tests et outillage, nettoyage, puis restructuration des apps et du modèle de données : projets, sujets et tags partagés, app dédiée aux images, découpage du parseur qmd).

Pistes envisagées ensuite, non planifiées :

- éditeur de notes assisté (insertion de projets, sujets et images depuis des listes),
- éditeur d'images simple (vectoriel et matriciel) et page détail d'une image avec les notes liées,
- vue calendrier des notes et accès direct à la note du jour,
- export et réimport de toutes les notes au format qmd.
