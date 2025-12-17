# Application de gestion générale

Application pour l'organisation quotidienne.

Projet DJANGO `app_gestion`, contenant des applications :

- `note_taking` pour la prise de notes,
- `todolist` pour la gestion de TODO.

## Prise de notes

Les notes sont organisés par jour, chaque jour étant un fichier quarto (`.qmd`).

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

Les titres sont cummulatifs, ce qui signifie qu'un texte contenu sous "Tag 2" hérite du projet, sujet et Tag 1. Par convention, même si un titre conient une virgule, il est considéré comme un tag à part entière (par exemple le titre "Conception, approvisionnement et fabrication" donnera le tag `Conception, approvisionnement et fabrication` et non les tags `Conception` et `approvisionnement et fabrication`).

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
