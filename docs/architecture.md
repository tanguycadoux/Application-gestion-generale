# Architecture

Ce document décrit l'organisation du code et les décisions structurantes du projet, avec leur raison. Le fonctionnement côté utilisateur (format des notes, tâches issues des notes…) est décrit dans le [README](../README.md) ; le suivi des évolutions se fait dans les [issues](https://github.com/tanguycadoux/Application-gestion-generale/issues) GitHub.

## Contexte

- Application **locale et mono-utilisateur** : pas d'authentification, réglages Django non durcis (`DEBUG`, `SECRET_KEY` en dur).
- Django, SQLite, rendu côté serveur. Front sans Node ; seule étape de build, la feuille Tailwind (voir la section Front).

## Front

- Rendu côté serveur par les gabarits Django ; pas d'étape de build JS.
- **Tailwind CSS** v4 pour le style, **Material Symbols Rounded** en SVG inline pour les icônes, **htmx** pour les mises à jour partielles. Le détail des versions et des points de chargement est dans le README.
- **Aucune ressource externe** (#217) : les notes sont privées, et le navigateur ne doit contacter aucun serveur tiers. La feuille Tailwind est compilée en local par `django-tailwind-cli` (CLI autonome de Tailwind, version épinglée par `TAILWIND_CLI_VERSION`, sans Node) depuis `assets/css/source.css`, dans `static/css/tailwind.css`, non versionnée ; la CI la construit dans un job à part. htmx est embarqué dans `static/vendor/htmx/`, avec sa licence et un README (source, empreinte d'intégrité), et chargé une fois par le gabarit de base. KaTeX (#99) est embarqué de la même façon dans `static/vendor/katex/`, chargé par le gabarit de base des notes. Une bibliothèque front s'ajoute de la même façon (CodeMirror, #89). Le téléchargement du CLI de Tailwind est une étape d'installation, pas une requête de l'application. Les icônes (#218) sont des fichiers SVG de Material Symbols (`static/icons/`, licence et README dans le dossier), téléchargés une fois par `python manage.py add_icon` et recopiés dans les pages par `{% icon %}` (`core/icons.py`) : pas de police chargée. Les icônes des toasts, créés en JavaScript, sont rendues par le gabarit de base dans des `<template>`, que le script clone. Garde-fous : un test refuse toute ressource externe dans les pages et les gabarits (hors contenu des notes), et le lanceur de tests (`app_gestion/test_runner.py`) fait échouer toute connexion réseau.
- Règle de style : tout en classes Tailwind (#79) ; CSS propre réservé à ce que Tailwind ne couvre pas : le HTML produit par le Markdown (`.rendered-content`, callouts) et les animations des alertes créées en JavaScript (bloc `@layer components` de `assets/css/source.css`). L'apparence des alertes est en classes Tailwind dans le script ; leurs boutons reprennent les classes des variantes du composant `button`, transmises par le gabarit de base (`{% button_variants_json %}`). Le détail est dans le README. Les éléments d'interface récurrents sont des composants partagés : balises d'inclusion de `core/templatetags/ui.py` (`{% load ui %}`), gabarits dans `core/templates/core/components/` (principes dans la section « Composants d'interface » plus bas). Le thème Tailwind (couleurs de Tailwind, toutes émises par `theme(static)`) et les styles de base sont dans `assets/css/source.css`.

## Apps et dépendances

```
app_gestion/   configuration : settings, urls, lanceur de tests sans réseau
core/          éléments communs : Project, Section, Tag, AppError, accueil,
               page Projets, gabarit de base, composants d'interface,
               calendrier mensuel, icônes, validateur HTML
images/        modèle Image, import et suppression des images
note_taking/   notes, analyse qmd, rendu, import et export, recherche,
               calendrier des notes, pages d'images
todolist/      tâches : arbre, avancement, calendrier, frise, tâches issues des notes
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
- `note_taking` ne connaît pas les tâches (#179). Après le recalcul des note parts d'une note, elle émet le signal `note_parts_processed` (`note_taking/signals.py`), dans la même transaction ; `todolist` l'écoute (`todolist/receivers.py`) et crée les tâches. `todolist` dépend donc de `note_taking` : le signal, `NotePart`, et `Note` pour le lien vers la note d'origine d'une tâche. Pour proposer une suite à l'enregistrement (#239), un receveur renvoie un `NoteFollowUp` (libellé et adresse, construite par l'app qui l'écoute) ; `process_note_parts` les range dans `note.follow_ups`, et la note redirige vers la première ou les cite dans le compte rendu d'import, sans connaître l'app qui les propose.
- Ce sens est vérifié par un test (`core/tests/test_dependencies.py`) : imports Python et noms d'URL cités dans les gabarits, hors tests et migrations.

## Éléments communs de `core`

| Module | Rôle |
|---|---|
| `models.py` | `Project` (nom unique, couleur, description), `Section` (niveau d'un chemin sous un projet, #295), `Tag`, partagés par les notes et les tâches |
| `sections.py` | chemins : saisie (`split_path`, `join_path`), création et reprise d'un chemin (`section_for`), ancêtres, sous-arbre et libellés (`with_ancestors`, `with_descendants`, `path_labels`), oubli des sections inutilisées (`forget_unused_sections`) |
| `tags.py` | `forget_unused_tags`, appelée par `reprocess_notes` |
| `app_registry.py` | ce que chaque app déclare dans son `AppConfig` : entrée du menu d'accueil, utilisations d'un projet (voir « Apps et dépendances ») |
| `templatetags/ui.py` | composants d'interface (`button`, `nav_link`, `tag_list`, `project_badge`, `icon`…), dates (`date_time`, `date_text`, formats `DATE_FORMATS`), couleurs des projets |
| `month_calendar.py`, `components/month_calendar.html` | grille d'un calendrier mensuel, partagée par les notes et les tâches : chaque app fournit son type de case et son gabarit (#167) |
| `forms.py` | formulaires des projets, et rendu en grille de `{{ form }}` (`GridFormRenderer`, réglage `FORM_RENDERER`, #132) |
| `icons.py`, `management/commands/add_icon.py` | icônes Material Symbols en SVG (`static/icons/`), et leur téléchargement (#218) |
| `codemirror.py`, `management/commands/vendor_codemirror.py`, `templatetags/vendor.py` | CodeMirror embarqué : liste des modules, vérification des empreintes, import map (#89) |
| `html_validator.py`, `management/commands/install_validator.py` | validateur HTML du W3C en local (#259) |
| `exceptions.py` | `AppError`, base des erreurs métier |

Les couleurs des projets (#162) sont des familles de Tailwind réservées aux projets. Un projet créé sans couleur, par une note ou une tâche, reçoit la moins utilisée. Seule la pastille (`project_badge`) les emploie.

## Organisation de `note_taking`

| Module | Rôle |
|---|---|
| `qmd/parser.py` | analyse du texte d'une note en note parts (`ParsedNote`, `ParsedPart`) ; **sans accès à la base** |
| `qmd/lists.py` | règle d'imbrication des listes de Pandoc (#229), partagée par le rendu et les sous-tâches issues des notes (#238) |
| `qmd/files.py` | lecture des fichiers `.qmd`, séparation du bloc d'en-tête (`split_front_matter`) |
| `services.py` | import, mise à jour, génération des note parts et des liens vers les images (accès à la base) |
| `signals.py` | `note_parts_processed`, émis après le recalcul des note parts (tâches issues des notes), et `NoteFollowUp`, la suite qu'un receveur propose (#239) |
| `rendering.py` | rendu HTML : Markdown filtré, références d'images, callouts et blocs Quarto |
| `importing.py`, `qmd/export.py` | import unifié (notes, images, archives) et export en archive Quarto |
| `note_calendar.py` | calendrier des notes, sur la grille de `core` |
| `exceptions.py` | erreurs métier (`NoteError` et sous-classes) |
| `management/commands/reprocess_notes.py` | recalcul des note parts de toutes les notes |

Les vues sont fines : elles délèguent aux services et n'attrapent que les erreurs métier.

## Organisation de `todolist`

| Module | Rôle |
|---|---|
| `models.py` | `Todo` : avancement, état terminé, propagation aux ancêtres (`update_ancestors_progress`), incohérences, signal d'échéance (`due_signal`) |
| `tree.py` | arbre des tâches en une requête (`children_map`), groupes et lignes du tableau ; chaque tâche y reçoit son parent et ses enfants déjà chargés (`Todo.tree`, #188) |
| `services.py`, `receivers.py` | tâches issues des notes, créées à l'écoute de `note_parts_processed` ; le receveur propose le bilan des tâches créées (`note_review`, #239) |
| `task_calendar.py` | calendrier des tâches : une tâche en cours à son échéance, une tâche terminée à sa date de complétion |
| `gantt.py` | frise de type Gantt du détail d'un parent (#168) |
| `templatetags/todo_ui.py` | affichage du tableau : indentation, temps restant, couleurs du signal d'échéance |
| `static/todolist/todo.js` | case à cocher : la vue renvoie les lignes modifiées, que la liste remplace sans recharger la page (#189) |

Le tableau des tâches (`task_table.html`, une ligne par `task_row.html`) sert à la liste et au détail d'un parent.

## Modèle de données

```
Note ──< NotePart >── Project          (core)
           │  │  └──── Section (option)  (core)
           │  └──<>── Tag              (core)
           └────<>─── Image            (images), via NotePartImageLink

Todo >── Project, Todo >── Section (option), Todo >─< Tag,
Section >── Project, Section >── Section (parent, option),
Todo >── Todo (parent, option)
```

- **`Note`** : une note par jour (`date` unique) ; `body` contient le texte de la note.
- **`NotePart`** : morceau de note partageant projet, section (la dernière du chemin) et tags, avec les titres de sa section (`heading_path`, #240). **Données dérivées** de `Note.body`.
- **`Project`, `Section`, `Tag`** : partagés par les notes et les tâches. Un projet a un nom unique, une couleur (#162) et une description. Une section est un niveau d'un chemin sous un projet (voir « Chemins sous un projet »).
- **`Todo`** (tâche) : titre, projet, section (son sujet) et tags, description, priorité, échéance ; avancement en pourcentage (`progress`), état terminé (`done`) et moment où elle l'est devenue (`completed_at`), avancement d'avant la coche, rendu au décochage (`progress_before_done`, #237) ; parent optionnel, pour les sous-tâches. Une tâche issue d'une note garde la date, le chemin et le texte de sa ligne (`note_part_date`, `note_path`, `note_part_text`), et son état dans la note (`note_state` : à revoir, revue, gardée sans sa ligne, écartée, #240). `Todo.objects` exclut les tâches écartées ; `Todo.all_objects` les compte.
- **`Image`** : nom de fichier d'origine (unique, sert de référence dans les notes), fichier affiché, source éditable optionnelle.

## Décisions

### La base fait foi, le qmd est un format d'échange (#24)

`Note.body` est le texte de la note, **sans bloc d'en-tête** (`---` / `date: …` / `---`). La date est celle de `Note.date`. Le bloc d'en-tête n'est lu qu'à l'import (vérification de la date) et sera régénéré à l'export (#64). Dans le formulaire web, un bloc d'en-tête éventuel est retiré, ou refusé si sa date diffère.

On ne stocke pas la note sous forme structurée (arbre de sections) : le découpage en note parts perd de l'information (ordre, origine des tags, mise en forme) et ne permet pas de régénérer la note. Le texte reste la source.

Export et import (#64, #114) : l'export produit une archive zip à la disposition d'un dossier Quarto (`AAAA-MM-JJ.qmd` à la racine, `images/<nom>`), qui forme un projet Quarto valide une fois dézippée ; chaque fichier est généré depuis la base (`note_taking/qmd/export.py`). Un seul formulaire d'import (`note_taking/importing.py`) accepte plusieurs fichiers et traite chacun selon son type : un `.zip` est l'archive de l'export, un `.qmd` une note, une image une image. Les images sont importées avant les notes, qui les citent. La base fait foi : une image déjà présente sous ce nom est gardée (le fichier importé est écarté, sans doublon, le nom étant unique) ; une note dont la date existe déjà n'est jamais remplacée sans confirmation : pour l'instant elle est ignorée et signalée dans le compte rendu (choix entre les deux versions : #115). Le remplacement volontaire d'une note par son fichier source reste sur la page de la note.

### Les note parts sont dérivées et recalculées

`process_note_parts` supprime et recrée les note parts d'une note, avec leurs liens (tags, images), à chaque enregistrement (import, mise à jour, formulaire), en tout ou rien (#221) : si l'analyse échoue, les note parts et les tâches d'avant restent intactes, et le texte de la note, déjà enregistré, n'est pas annulé. Conséquences :

- aucune donnée saisie ne doit être rattachée à une note part, car elle serait perdue au prochain enregistrement ;
- après une évolution du parseur, `python manage.py reprocess_notes` recalcule toutes les notes (`--dry-run` pour simuler).

### Tâches issues des notes

Une case vide `- [ ] texte`, où qu'elle soit, donne une tâche ; dans une branche `todo: true`, chaque élément de liste en donne une (#297). Ces tâches sont créées par `todolist`, à l'écoute du signal `note_parts_processed` (voir « Apps et dépendances »).

- Le titre est le texte de la ligne sans son marqueur de liste ni sa case (#222). Une case cochée n'est pas une tâche : elle est ignorée (#297, qui remplace « une case cochée ne termine pas la tâche »), comme une ligne qui n'est pas un élément de liste ; les cases d'un bloc de code aussi (`lines_of`).
- Une ligne imbriquée sous un élément de liste, selon la règle des sous-listes du rendu (#229), donne une sous-tâche de la tâche la plus proche au-dessus (#238), sur plusieurs niveaux ; une ligne sans marqueur sous un élément, suite de son texte pour Pandoc, n'est pas une tâche. Le texte d'un élément parent, tâche ou non, entre dans le chemin de la ligne. Le parent n'est posé qu'à la création : il a pu être choisi à la main ensuite.
- La tâche reprend le projet et la section de la note part. Ses tags sont ceux de la note part, sans `TODO`. Elle n'a pas d'échéance (#239) : la date de la note la mettait en retard dès le lendemain.
- **Identité** (#240) : une tâche générée est identifiée par la date de la note, le chemin de sa ligne et son texte, pas par une clé étrangère vers sa note part, recréée à chaque enregistrement. Le chemin est fait des titres de la section tels qu'écrits, puis des éléments parents : « Test › BLABLA › P » pour la ligne « F » sous « P ». Une même ligne sous un autre sujet ou sous un autre parent est donc une autre tâche. Une tâche créée avant #240, sans chemin, est reprise par sa date et son texte au prochain enregistrement de sa note (`reprocess_notes` les reprend toutes).
- **Cycle de vie** (#240) : une tâche créée est **à revoir**. Tant qu'une note a des tâches à revoir, son enregistrement (formulaire, remplacement par le fichier source) redirige vers son bilan (`todolist:note_review`), et un import le cite dans son compte rendu. Le bilan se calcule depuis la base, sans session. Il présente :
  - les tâches dont la ligne est dans la note : échéance, priorité, projet et sujet ; enregistrer les rend **revues**, même sans échéance. « Plus tard » les laisse à revoir ;
  - les tâches dont la ligne a disparu (modifiée, déplacée ou retirée) : une tâche revue dans ce cas redevient à revoir. On la garde (**gardée sans sa ligne**, plus jamais présentée), on l'écarte, ou on la remplace par la tâche d'une nouvelle ligne : l'ancienne prend son chemin et son texte, garde avancement, échéance et sous-tâches, reçoit celles de la nouvelle, qui est supprimée. Son titre suit la ligne, sauf s'il a été renommé à la main.
- **Tâche écartée** (#240, #290) : retirer une tâche dont l'arbre (elle et ses sous-tâches) contient une tâche issue d'une note écarte l'arbre en entier, tâches saisies à la main comprises, pour que le rétablir le rende intact (`remove_task`) ; la page de la tâche dit alors « Écarter » au lieu de « Supprimer » (`removal_dismisses`). Un arbre saisi à la main est supprimé ; une tâche déjà écartée qu'il portait est détachée. Une tâche écartée n'est plus affichée nulle part (`Todo.objects` l'exclut : listes, sous-tâches, avancement du parent, formulaires) ni comptée dans les usages d'un projet (`ProjectUsage.exclude`), et le prochain enregistrement de la note ne la recrée pas. Un projet utilisé seulement par des tâches écartées se supprime avec elles (`protect_unless_dismissed`).
- **Rétablir** (#290) : la liste des tâches a une section repliée « Écartées », une ligne par tâche écartée dont le parent ne l'est pas (`dismissed_rows`). « Rétablir » (`restore_task`) rétablit aussi ses sous-tâches écartées, ce que la confirmation et le message disent. Chacune redevient revue si sa ligne est encore dans sa note, gardée sans sa ligne sinon ; une tâche saisie à la main le redevient. La tâche retrouve son parent s'il est encore affiché ; s'il est écarté, elle revient à la racine, et le message le signale. Pas de suppression définitive : la ligne, si elle est encore dans la note, reviendrait en tâche au prochain enregistrement, ce que l'écart sert justement à empêcher.

### Avancement, état terminé et incohérences des tâches (#164, #165)

- L'avancement d'une tâche sans sous-tâche se saisit, et elle est terminée à 100 %. Celui d'un parent se calcule : c'est la moyenne arrondie de ses enfants, propagée aux ancêtres à chaque enregistrement.
- Un parent se coche à la main. Il se décoche dès qu'un de ses enfants n'est plus terminé. À 100 % et non coché, il est « à valider ».
- Les écarts entre une tâche et ses sous-tâches ne sont pas empêchés mais signalés, des deux côtés : échéance d'une sous-tâche après celle du parent, projet différent. Seule une boucle parent-enfant est refusée.
- Supprimer une tâche supprime ses sous-tâches ; la confirmation et le message le disent (#223).
- Une seule règle d'urgence, `Todo.due_signal` : terminée, en retard, proche (sous 3 jours) ou normale (#189).

### Projets, sections et tags partagés (#19, #20, #295)

- Un même modèle pour les notes et les tâches, fusionnés par nom lors de la migration.
- Une **section appartient à un projet** (#295) : « Calcul thermique » sous deux projets est deux sections. Elle remplace le sujet, qui était global ; voir « Chemins sous un projet ».
- La casse est respectée (« Thermique » ≠ « thermique »).
- Un tag devenu inutilisé reste en base, mais n'est pas proposé dans la recherche. Une section que plus rien n'utilise est supprimée à l'enregistrement d'une note (`forget_unused_sections`).
- Les tags vides (`tags: []`) sont ignorés.

### Chemins sous un projet (#287, #295)

Un chemin est une suite de niveaux sous un projet : « Réunion › Préparation ». C'est un **arbre de lignes** (`Section` : projet, parent facultatif, nom), pas un texte à séparateurs : un « / » dans un titre (« Rapport RT17/A ») ne peut pas passer pour un séparateur, et renommer un niveau fait suivre ses descendants. Modèle repris des tags hiérarchiques de `research-paper-relationship-graph`, avec les parents comme vraies lignes.

- Un niveau est **unique sous son parent, casse ignorée** ; un niveau déjà connu garde la casse de sa première écriture (`section_for`). Le `LOWER` de SQLite ne replie que l'ASCII : la comparaison complète se fait en Python, les contraintes de la base sont un filet.
- Le séparateur n'existe qu'à la **saisie** (« / » entre niveaux, « // » pour un « / » littéral : `split_path`, `join_path`) et à l'**affichage** (« › »). Les notes ne passent pas par ce texte : leurs titres donnent directement les niveaux.
- Supprimer un niveau supprime ses descendants. `Section.project` est en cascade ; `NotePart.section` est protégé, `Todo.section` passe à vide.
- `core` ne connaît aucune app : `forget_unused_sections` lit les clés étrangères qui mènent à `Section` sur le modèle, sans importer les apps.
- **Dans les notes** (#296) : `#` donne le projet, `##` à `######` les niveaux du chemin, sans limite de profondeur (`NoteParser.current_path`). Les titres ne donnent plus de tags : seuls les blocs `{.metadata}` en donnent, avec une portée sur la branche, jamais un niveau. `heading_path` garde tous les titres tels qu'écrits, dont dépend l'identité des tâches (#240).
- **Titres qui sautent un niveau** (#305) : `NoteParser.check_level` relève, dans `ParsedNote.warnings`, un titre de niveau plus profond que le plus profond au-dessus de lui plus un, et un titre sans projet (`#`) au-dessus. L'analyse les accepte telle quelle (le chemin se fait des titres, pas de leur niveau, et un renommage repère un titre par la suite des titres au-dessus de lui, #299) et **ne réécrit jamais le texte**. `process_note_parts` les range dans `note.warnings`, comme les suites proposées (`note.follow_ups`) : l'enregistrement les montre en un avertissement (`warnings_message`), le compte rendu d'import les liste.
- **Cases à cocher et `todo`** (#297) : le titre `TODO` n'a plus de sens propre, c'est un niveau du chemin. Le bloc `{.metadata}` accepte `todo: true` ou `todo: false` (`Level.todo`) : même portée que les tags, le niveau le plus profond qui en parle l'emporte. Une branche `todo: true` donne le tag `TODO` à ses note parts (`NoteParser.current_tags`), sans modèle de plus ; `is_todo_part` le lit. Un bloc ne remplace plus les tags d'un niveau que s'il a une clé `tags` : une clé inconnue reprenait les tags périmés d'un bloc d'avant.
- **Conversion des anciennes sections TODO** (`convert_todo_sections`, `note_taking/qmd/todo_sections.py`, commande dans `todolist`) : retire le titre `TODO` et passe chaque élément de sa section en case, en gardant les fins de ligne. Sans `--apply`, aperçu seulement. Retirer le titre range la liste sous le titre frère qui le précédait (`### Compte rendu` puis `### TODO` : le titre `TODO` avait remplacé son frère) : le chemin des tâches change, donc leur identité (#240). La commande garde les titres d'avant et d'après de chaque morceau de section (`Chunk`) et **range les tâches déjà créées sous leur nouveau chemin** (même fiche : avancement, échéance, parent, état), avant de recalculer les notes. Une tâche revue qui perdrait quand même sa ligne annule tout. Les cases vides hors section TODO deviennent des tâches à revoir ; une section qui n'est pas qu'une liste (paragraphe, bloc, case cochée, code) est signalée et laissée telle quelle.
- **Chemin d'une tâche** (#298) : le champ des formulaires est un texte, `SectionPathField` (`core/forms.py`), dont la valeur nettoyée est la liste des niveaux (`split_path`). Le formulaire (`SectionPathForm`, `todolist/forms.py`) crée le chemin sous le projet choisi **à l'enregistrement** (`section_for`), jamais pendant la validation : un formulaire refusé ne laisse pas de section. Changer le projet d'une tâche replace son chemin sous le nouveau projet. L'autocomplétion est une `<datalist>` native (`SectionPathInput`, `core/forms/widgets/section_path.html`), alimentée par `path_suggestions` en une requête : chaque chemin une fois, avec les projets qui le portent en libellé de l'option.
- **Filtre de la liste des tâches** (#298) : `?chemin=<id>` garde les tâches du niveau et de ses descendants (`with_descendants`). Chaque tâche reste sous ses parents pour que l'arbre garde son sens (`restrict_to_sections`, `todolist/tree.py`) ; un parent qui ne répond pas au filtre est une ligne atténuée (`TaskRow.muted`). Pas encore de filtre sur le calendrier et la frise : à reprendre avec le composant d'arbre (#302) et les filtres des tableaux (#178).
- **Arbre et renommage d'un niveau** (#299) : la page « Chemins » d'un projet (`core.views.project_paths`, `core/section_tree.py`) dresse l'arbre avec ses compteurs, descendants compris ; chaque app déclare ce qui utilise un niveau (`section_usages` de son `AppConfig`, `core/app_registry.py`), comme pour les projets, et `core` compte sans la connaître. Le renommage (`core.views.rename_section`) se fait en trois temps : le nom (`check_new_name` : vide, identique ou pris sous le même parent refusé, casse seule permise), le bilan, l'écriture. `core` ne connaît pas les notes : `note_taking` déclare un `SectionRenamer` (`occurrences`, `rename`) dans son `AppConfig`. **Suppression** (`core.views.delete_section`, POST seulement) : refusée si `TreeRow.total` n'est pas nul, c'est-à-dire si le niveau ou un descendant sert à une note part ou à une tâche non écartée ; sinon `Section.delete()` emporte les descendants (cascade). Le bouton est désactivé sur un niveau utilisé, avec `aria-describedby` vers le texte de l'usage (`TreeRow.usage_id`). Une tâche écartée n'est pas comptée : son `section` passe à vide (`SET_NULL`), son chemin écrit (`note_path`) reste.
- **Réécriture des titres** (`note_taking/renaming.py`) : un titre est repéré par la suite des titres au-dessus de lui, projet compris (`headings`, `find_headings`), pas par son niveau ; ceux des blocs de code et des callouts ne comptent pas, et le texte entier du titre (attributs compris) est le nom du niveau, comme pour le parseur. `rewrite_titles` garde dièses, espaces et fins de ligne. `rename_titles` vérifie que chaque titre choisi est encore là (sinon rien n'est écrit : la note a changé depuis le bilan), puis réécrit et recalcule chaque note, en une transaction. **Tout renommé** : la vue renomme la `Section` en place avant d'écrire les notes, donc ses descendants et les tâches saisies à la main qui la portent suivent. **Renommage partiel** : l'ancien niveau garde ses notes, le nouveau naît au recalcul ; les tâches déjà créées gardent leur niveau choisi.
- **Les tâches suivent** : avant le recalcul d'une note, `note_taking` envoie `note_headings_renamed` (note, ancien et nouveau texte). `todolist` (`follow_renamed_headings`) compare les lignes de tâches des deux textes, note part par note part (`renamed_identities`), et range les tâches déjà créées sous leur nouveau chemin (`move_tasks`, en deux temps pour la contrainte d'unicité). Même fiche : avancement, échéance, parent, état. Si le renommage fusionnait ou séparait des parties d'une note qui a des tâches (deux titres qui ne diffèrent que par la casse, par exemple), les lignes ne se retrouvent plus : la note est refusée (`NoteRenameError`), et rien n'est écrit.
- **Recherche des note parts** : les chemins proposés sont ceux des note parts, avec leurs parents implicites (`with_ancestors`) ; choisir un niveau cherche aussi ses descendants (`with_descendants`). Libellés « Projet › Réunion › Préparation » en une requête (`path_labels`).
- `reprocess_notes` recalcule les note parts, puis supprime les tags que plus rien n'utilise (`core/tags.py`) : un enregistrement de note ne supprime jamais de tag, pour ne pas faire disparaître un tag créé à la main. Les tâches déjà créées gardent leur section : une tâche générée prend celle de sa note part à sa création.

### Images (#25, #26)

- Modèle dans l'app `images` ; les **pages restent dans la prise de notes**.
- Une image est référencée dans une note par son **nom de fichier**, quel que soit le dossier écrit. À l'analyse, la référence devient `image:<pk>` dans le contenu de la note part.
- Le nom se tire du chemin par une seule fonction, `rendering.image_name`, commune à l'analyse, au rendu et à l'export (#220) : dossier ignoré, `\` traité comme `/`, et `None` pour une URL externe (`http(s)://`, `data:`, chemin absolu). Une image sur un autre serveur n'est pas chargée : le rendu en fait un lien vers son adresse (`remote_images_as_links`).
- Le **format** (vectoriel ou matriciel) se déduit de l'extension du fichier (`is_vector`), l'**origine** de la présence d'une source (`is_editable`) : ce sont deux notions indépendantes, sans champ dédié.
- Le lien vers les images est porté par la **note part**, là où l'image est utilisée : on sait dans quel projet, sujet et avec quels tags elle apparaît. `Note.images` en est déduit.

### Suppression protégée

Un objet utilisé ne peut pas être supprimé (`on_delete=PROTECT`) :

- un **projet** utilisé par une note part ou une tâche ;
- une **section** utilisée par une note part (celle d'une tâche passe à vide à la suppression, elle est facultative) ;
- une **image** utilisée par une note part (via `NotePartImageLink`).

Django refuse la suppression (`ProtectedError`) et l'admin liste les éléments concernés.

Dans l'interface, une image se supprime depuis sa page de détail (#85) : le bouton est désactivé, avec la raison, tant que l'image est utilisée. Le service `images.services.delete_image` s'appuie sur la même protection : il traduit la `ProtectedError` en erreur métier (`ImageInUseError`), sans connaître les apps qui utilisent les images, et n'efface les fichiers qu'une fois la suppression validée en base.

### HTML des notes filtré (#241)

Le HTML qu'écrit l'utilisateur, directement ou par le Markdown, passe par une liste blanche (`nh3`, dans `render_plain_markdown`) : balises d'un document (texte, titres, listes, tableaux, images, liens, code, `details`…), attributs `class`, `id`, `title`, `href`, `src`, `alt`, `width`, `height`, `style` limité à `text-align` sur les cellules, et URL en `http`, `https`, `mailto` ou relatives. Un script, un gestionnaire `on…`, un cadre ou un lien `javascript:` est retiré : il s'exécuterait dans la page et pourrait envoyer les notes ailleurs. Le HTML des blocs Quarto (callouts, grilles, colonnes, icônes) est construit autour, à partir de valeurs échappées ou contrôlées, et n'est pas filtré.

Après le filtrage, chaque image du contenu reçoit `loading="lazy"` et `decoding="async"` (#225) : une note longue ne charge que les images proches de l'écran. La liste des images fait de même.

### Rendu fidèle à Quarto (M11)

Le rendu suit le Markdown de Pandoc, celui de Quarto, et non les règles propres à Python-Markdown. Un écart se corrige par une extension Markdown de `rendering.py`, testée sur les résultats de Pandoc.

- Sous-listes (#229) : un élément est imbriqué si son marqueur commence au moins à la colonne du texte de l'élément parent (2 espaces après `- `, 3 après `1. `). `PandocListsExtension` réindente les listes par multiples de 4, seul pas que comprend Python-Markdown ; un changement de type de liste commence une autre liste (`sane_lists`). La règle est dans `qmd/lists.py` : les sous-tâches issues des notes (#238) la suivent aussi.
- Cases à cocher (#231) : un élément qui commence par `[ ]`, `[x]` ou `[X]` suivi d'un blanc devient une case dans un `<label>`, comme dans Pandoc ; une liste à puces faite uniquement de cases reçoit la classe `task-list`, sans puces. `TaskListExtension` pose le `<label>` ; la case (`<input type="checkbox" disabled>`) n'est ajoutée qu'après le filtrage nh3, dont la liste blanche n'accepte aucun champ de formulaire. Les cases sont désactivées : la page affiche la note sans la modifier. Une tâche issue d'une ligne à case garde son propre état : une case cochée ne la termine pas (#222, voir #237).
- Légendes de tableau (#230) : un paragraphe qui commence par `:` ou `Table:`, juste avant ou juste après un tableau, avec ou sans ligne vide, devient son `<caption>` ; celle d'avant l'emporte. Des attributs `{#tbl-x .classe}` en fin de légende vont au tableau. `TableCaptionExtension` sépare d'abord une légende collée au tableau, puis déplace le paragraphe dans le tableau. La numérotation croisée de Quarto (« Table 1: » pour un tableau `#tbl-…`) n'est pas reprise : une note part est rendue seule, sans le reste de la note.
- Exposants, indices et barré (#271) : `^…^` en `<sup>`, `~…~` en `<sub>`, sans espace dans le contenu sauf échappée (`\ `, espace insécable) ; `~~…~~` en `<del>`, reconnu avant l'indice, qui utilise lui aussi le tilde. `\^` et `\~` restent du texte. Les motifs inline de `SuperscriptSubscriptExtension` passent avant l'emphase, qui reste rendue à l'intérieur. Une formule LaTeX (#99) passe avant : `$x^2^$` ne produit pas d'exposant HTML.
- Formules LaTeX (#99) : `$…$` en ligne (pas d'espace après le premier `$` ni avant le second, pas de chiffre juste après) et `$$…$$` en bloc, éventuellement sur plusieurs lignes. `MathExtension` garde la formule telle qu'écrite, sous la forme de Pandoc avec MathJax, celle de Quarto : `<span class="math inline">\(…\)</span>` ou `math display` et `\[…\]`. Ses motifs passent avant tous les autres sauf le code : ni l'emphase, ni les exposants, ni les caractères échappés ne touchent une formule ; `\$` reste un dollar. KaTeX, embarqué dans `static/vendor/katex/` (polices `woff2` seulement), affiche la formule dans le navigateur : `note_taking/static/note_taking/math.js`, chargé par le gabarit de base des notes, rend les formules à l'ouverture de la page et après chaque échange htmx (`htmx:load`). Sans JavaScript, la formule reste lisible telle qu'écrite. KaTeX plutôt que MathML : rendu identique d'un navigateur à l'autre, et la syntaxe LaTeX des notes s'affiche sans conversion côté serveur.

### Éditeur des notes (#89)

L'éditeur est **CodeMirror 6**, embarqué dans `static/vendor/codemirror/` (aucun CDN), et non un `<textarea>` enrichi : les suggestions dans le texte (projets, chemins, images, plus tard les notes), les soulignements de l'assistant (M18) et l'historique d'annulation après une insertion ne se font pas proprement sur un `<textarea>`.

- **Le `<textarea>` reste** : `editor.js` (module ES, `note_taking/templates/note_taking/note/form.html`) le cache et le remplace par CodeMirror, qui le tient à jour à chaque frappe ; c'est lui que le formulaire envoie. Si le module ne se charge pas, on écrit dans le `<textarea>`.
- **Garde-fous** (#228) dans `note_form.js`, un script classique indépendant de CodeMirror : Ctrl+S envoie le formulaire, et quitter la page avec un texte ou une date modifiés déclenche l'avertissement du navigateur (`beforeunload`), levé à l'envoi. Une page rendue avec des erreurs porte `data-unsaved` : ce qu'elle affiche n'est pas enregistré.
- **Fichiers** : un dossier par paquet npm (`index.js`, le fichier ES d'entrée, et `LICENSE`), liste, versions et empreintes dans `packages.json`. `python manage.py vendor_codemirror` télécharge les archives depuis le registre npm, vérifie leur empreinte (`dist.integrity`) et réécrit `packages.json` et le README du dossier ; c'est une étape d'installation, l'application ne contacte jamais Internet. Une import map (`{% codemirror_importmap %}`, `core/templatetags/vendor.py`), placée avant le script sur les seules pages d'une note, renvoie chaque nom de module vers `static/`. `.gitattributes` laisse ces fichiers octet pour octet (sans conversion des fins de ligne), pour que les empreintes restent exactes.
- **Ajouter un module** : une ligne dans `packages.json` (nom, version, fichier d'entrée), puis `vendor_codemirror`. `core/tests/test_codemirror.py` vérifie que les fichiers correspondent à leurs empreintes et que tout module importé par un fichier embarqué ou par `editor.js` est dans la liste. Les versions retenues ont au moins deux semaines.
- **Le strict nécessaire** : `state`, `view`, `commands`, `language`, `search` et l'analyseur `@lezer/markdown` (plus `streamparser` et les petites dépendances). `@codemirror/lang-markdown` est écarté : il fait charger l'analyseur HTML, donc CSS et JavaScript, pour du HTML que les notes ne contiennent pas ; `editor.js` construit le langage Markdown (`Language`) avec les cases `- [ ]` et le barré. Le texte du panneau de recherche est traduit en français (`EditorState.phrases`).
- **Mise en page** : la page d'une note est une colonne de la hauteur de la fenêtre (`flex h-full flex-col`), et le formulaire, sans grille (un seul champ large), prend la place restante : le texte défile dans l'éditeur, pas dans la page. Les classes Tailwind (bordure, fond, anneau de mise au point par `focus-within`) sont sur un conteneur créé par `editor.js`, pas sur l'élément racine de CodeMirror, dont il réécrit lui-même la classe. La coloration reprend les variables de couleur de Tailwind (`var(--color-blue-900)`), dans le respect des familles de couleurs (#128).
- **Suite** (M13) : les suggestions (`@codemirror/autocomplete`) pour #91 et #92, le collage d'une capture (#196), la continuation des listes avec Entrée.
- **Listes de suggestions** (#90) : trois vues JSON en lecture seule, que l'éditeur interrogera pendant la frappe. `core:project_suggestions` (`/projets/suggestions/?q=`, nom et couleur), `core:section_suggestions` (`/chemins/suggestions/?projet=&chemin=&q=` : les niveaux sous un chemin du projet nommé, les premiers niveaux si `chemin` est vide, rien si le projet ou un niveau n'existe pas ; `chemin` s'écrit avec « / » comme à la saisie d'une tâche) et `note_taking:image_suggestions` (`/note_taking/images/suggestions/?q=`, nom, référence `images/<nom>` à écrire et adresse de la vignette). Les projets et chemins sont dans `core` (`core/suggestions.py`), qui ne connaît pas les notes ; les images dans `note_taking`, qui référence les images. Au plus 50 résultats, ceux qui commencent par la saisie avant les autres, casse et accents ignorés (comparés en Python, le `LOWER` de SQLite ne replie que l'ASCII). Rien n'est créé : un nom nouveau reste créé à l'enregistrement de la note.

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
- **Accessibilité intégrée** : un élément réduit à une icône reçoit son libellé en `aria-label`, et le lien de menu actif reçoit `aria-current="page"`. Le gabarit de base nomme le menu (`<nav aria-label="Menu principal">`) et commence par un lien d'évitement « Aller au contenu » vers `<main id="contenu">`, masqué hors focus (#191).
- **Tests** : chaque composant a des tests du HTML rendu (`core/tests/test_components.py`), qui servent aussi de référence pour ses classes.

## Conventions de travail

### Tests

- `python manage.py test` ; tests dans un paquet `tests/` par app.
- **Tests d'abord** : avant de modifier un comportement, un commit ajoute les tests du comportement attendu, marqués `@unittest.expectedFailure` ; le commit de correction retire le décorateur.
- **Élagage en fin de milestone** : une issue, traitée en dernier, repasse sur les tests ajoutés pendant le milestone. Elle supprime les tests d'absence d'une chose retirée qui n'a pas de raison de revenir (un bouton, un panneau), garde ceux qui protègent une règle transversale ou une faille (ils échoueraient si un nouveau gabarit l'enfreignait), et fusionne les tests redondants.
- Le parseur est couvert par une note d'exemple (`note_taking/tests/data/exemple.qmd`) dont le résultat attendu est figé (`exemple.json`, régénérable avec `UPDATE_GOLDEN=1`, diff à relire).

### Outillage et CI

- `ruff` (lint et formatage, configuration dans `pyproject.toml`), `mypy` avec `django-stubs` (`mypy.ini`).
- `djlint` vérifie les gabarits (`djlint --lint`, configuration dans `pyproject.toml`, quelques codes ignorés par fichier avec leur raison). Son formatage automatique n'est pas utilisé : il coupe les attributs et ajoute des espaces dans le HTML produit (titres d'onglet, éléments en ligne), ce que les tests et le rendu remarquent (#242).
- `coverage` mesure la couverture des tests, sans seuil bloquant (`coverage run manage.py test`, puis `coverage report`).
- La CI GitHub Actions lance `ruff check`, `ruff format --check`, `mypy`, `djlint --lint`, `makemigrations --check`, les tests avec la couverture (validation HTML comprise) et la construction de la feuille Tailwind à chaque PR.
- Dependabot (`.github/dependabot.yml`) propose chaque semaine les mises à jour des dépendances `pip` et des GitHub Actions, les mineures et correctives regroupées dans une seule PR.
- `main` est protégée : une PR ne peut être mergée que si la CI passe et que la branche est à jour.
- **Validation HTML** (#259) : le validateur du W3C (Nu Html Checker, `vnu.jar`) tourne **en local**, jamais en ligne, car le validateur en ligne recevrait le contenu des notes. `python manage.py install_validator` le télécharge (paquet npm `vnu-jar`, version et intégrité épinglées par `VNU_VERSION` et `VNU_INTEGRITY`) dans `.vnu/`, non versionné ; il demande Java. `core/tests/test_html_validation.py` valide alors les pages principales, rendues avec des données de test ; sans validateur, ce test est ignoré. La CI l'installe et le lance à chaque PR. La dernière issue d'un milestone qui touche au HTML vérifie qu'il passe et en étend la liste de pages si besoin.

### Git

- Une branche par issue, partie de `main` à jour ; pas de PR empilées.
- Messages au format Conventional Commits, en français (`type(portée): description`).
- Merge par merge commit (le commit de formatage est référencé dans `.git-blame-ignore-revs`).

### Migrations de données

- Une migration de données n'importe pas le code de l'application (les modèles et le parseur évoluent) : elle utilise `apps.get_model` et, si besoin, une copie figée des fonctions utiles.
- Elle échoue sans rien modifier si les données ne sont pas dans l'état attendu, plutôt que de perdre de l'information.
- Avant la PR, elle est vérifiée sur une **copie** de la base réelle (comparaison avant / après, en SQL).
- Avant de l'appliquer : sauvegarder `db.sqlite3`.
