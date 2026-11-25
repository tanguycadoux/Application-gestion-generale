# Écarts à Pandoc

Le rendu des notes suit le Markdown de Pandoc, celui de Quarto (voir [`architecture.md`](architecture.md), « Rendu fidèle à Quarto »). Ce document liste les cas où il s'en écarte.

**Règle** : toute issue qui s'écarte de Pandoc ajoute sa ligne ici.

À l'export (#64), le texte de la note est écrit **tel quel**, sauf le bloc d'en-tête (la date), ajouté, l'extension `.qmd` des liens entre notes et le chemin des images : dans le fichier exporté, c'est Pandoc ou Quarto qui décide. La dernière colonne dit ce que cela donne.

## Écarts voulus

| Syntaxe | Pandoc ou Quarto | Application | Raison | Issue | À l'export |
|---|---|---|---|---|---|
| `[](https://…)`, lien sans texte | lien vide : rien ne s'affiche | l'adresse, comme `<https://…>` ; « Note du … » pour une note ; le titre visé, sinon l'ancre, pour `[](#ancre)` | un lien vide est presque toujours un oubli, et l'adresse serait perdue à la lecture | #467 | lien vide |
| `[texte](https://…)` | même onglet par défaut (`link-external-newwindow: false`) | nouvel onglet, et une flèche ↗ | ne pas quitter la note | #438 | même onglet |
| `[texte](AAAA-MM-JJ)` | lien relatif ordinaire | page de la note ; lien rouge vers sa création si elle n'existe pas | lier les notes entre elles | #206 | `.qmd` ajouté, que Quarto suit |
| `![…](https://…)`, image d'un autre site | image affichée | lien vers l'image | aucun serveur tiers n'est contacté | #220, #458 | image affichée, chargée depuis son site |
| HTML : `<script>`, `<iframe>`, `on…`, `javascript:` | gardé | retiré | il s'exécuterait dans la page | #241 | gardé |
| Titre souligné (`=====`, `-----`) | titre | texte | une liste à l'élément vide (`-`) ferait un titre ; le découpage ne connaît que `#` | #124 | titre |
| Niveau des titres | `#` donne `h1` | `#` donne `h2`, et ainsi de suite | la page a son propre `h1` | | niveaux d'origine |
| `::: {.metadata}` | bloc ordinaire | pastilles des tags | métadonnées de l'application | | bloc ordinaire |
| Numéros des tableaux et figures | sur tout le document | repartent de 1 à chaque rendu : la note, ou l'extrait seul | un extrait est rendu sans le reste de la note | #278 | numérotés par Quarto |
| Liste dont certains éléments seulement sont suivis d'une ligne vide | un seul élément aéré aère toute la liste ; une ligne vide entre deux sous-éléments n'aère que la sous-liste | seuls les éléments voisins de la ligne vide sont aérés, le parent des sous-éléments aussi | règle de Python-Markdown ; écart connu, non traité | #482 | règle de Pandoc |
| Images d'une figure en colonnes | 1a, 1b | leur légende, sans numéro | écart connu, non traité | #278 | 1a, 1b |

## Syntaxes non prises en charge

Le rendu les laisse **en texte**. Elles restent dans la note et fonctionnent à l'export. Côté application, vérifié le 2026-11-25 ; côté Pandoc et Quarto, d'après leur documentation.

| Syntaxe | Pandoc ou Quarto | Application |
|---|---|---|
| `[^1]`, `^[…]` | note de bas de page | texte |
| `"…"`, `--`, `...` | guillemets, tirets et points de suspension typographiques (`smart`) | tels quels |
| `Terme` puis `: définition` | liste de définitions | texte |
| `[texte]{.classe}` | portion de texte avec attributs | texte |
| `\| ligne` | bloc de lignes | texte |
| `+---+---+` | tableau en grille | texte |
| `\` en fin de ligne | retour à la ligne | texte (deux espaces en fin de ligne fonctionnent) |
| `@cle`, `[@cle]` | citation bibliographique | texte |
| `(@étiquette)` dans une phrase | renvoi à un exemple numéroté | texte (#325) |
| `{{< … >}}` | shortcode de Quarto | texte |
| `::: {.classe}`, `.panel-tabset`… | bloc, onglets | le contenu, avec les `:::` visibles ; les callouts, colonnes et métadonnées, eux, sont rendus |
| `\newpage`, LaTeX hors formule | LaTeX brut | texte |
| `` ```{python} `` | cellule exécutée | bloc de code, jamais exécuté |
