"""Pages valides selon le validateur HTML du W3C, lancé en local (#259).

Ignoré tant que le validateur n'est pas installé (`python manage.py
install_validator`, Java requis) ; la CI l'installe et le lance à chaque PR.
Les pages sont rendues avec des données de test, jamais la base réelle.
"""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import html_validator
from core.models import Project, Section, Tag
from core.sections import section_for
from images.models import Image
from note_taking.models import Note, PendingProjectRename
from note_taking.services import process_passages
from todolist.models import Task

from .debug_urls import DebugUrlsTestCase

TODAY = timezone.localdate()

NOTE_BODY = """# ASTERICS
## Réunion
### Ordre du jour
::: {.metadata}
tags: [suivi]
:::
- Point **gras** et *italique*, [lien](https://exemple.org)
- Code `x = 1`

| Colonne | Valeur |
|:--|--:|
| a | 1 |

::: {.callout-note}
## Extrait
Texte du callout.
:::

::: {.columns}
::: {.column width="40%"}
Gauche
:::
::: {.column}
Droite
:::
:::

::: {layout-ncol=2 #fig-banc}
![Vue A](images/banc.png){width=80%}

![Vue B](images/banc.png)

Légende commune
:::

![Vue **seule**, H<sub>2</sub>O et $x^2$](images/banc.png){width=50% fig-alt="Banc"}

Dans une ligne ![icône](images/banc.png), en lien
[![vue](images/banc.png)](https://exemple.org), distante
![logo](https://exemple.org/logo.png), [gras **ici**](mailto:a@exemple.org).

Sans texte (#467) : [](https://exemple.org/a?b=1&c=2), [](#voir-le-site), [](2999-01-01).

### Voir [le site](https://exemple.org)

```python
print("<b>")
```

Voir @tbl-retreint et @fig-banc.

- Sous-liste
  - à 2 espaces
- [ ] Case vide
- [x] Case cochée

1. Élément [souligné]{.underline}

   - sous-liste après une ligne vide
2. Élément suivant (#482)

1. Code sous un élément (#489)

   ```python
   - [ ] pas une case
   ```

> 1. Liste d'une citation (#490)
>    - sous-élément

- Élément

  suite
#### Titre collé à un élément (#491)

Le [plan](C:\\Docs\\plan.pdf), le [](\\\\serveur\\partage\\rapport.docx) (#496).

| Matériau | Rétreint |
|---|---|
| Cu | 3.2 |

: Rétreint (10^-6^/K), H~2~O, ~~ancien~~ {#tbl-retreint}

Formule $\\alpha_{Cu} < 1$ et en bloc :

$$
\\begin{aligned}
E_i &= E_z\\\\
E_j &= E_x
\\end{aligned}
$$

::: {.metadata}
todo: true
:::
- Relire le compte rendu
"""


@unittest.skipUnless(
    html_validator.is_available(),
    "validateur HTML absent : python manage.py install_validator (Java requis)",
)
class HtmlValidationTests(TestCase):
    def setUp(self):
        project = Project.objects.create(name="ASTERICS", color="teal")
        other = Project.objects.create(name="PDS1", color="rose")
        self.image = Image.objects.create(name="banc.png", file="note_images/banc.png")
        self.note = Note.objects.create(date=TODAY, body=NOTE_BODY)
        process_passages(self.note)
        # Une note qui cite celle du jour (#207) et une note absente (#206), avec du
        # texte sans projet (#385), et un titre de projet renommé (#170).
        self.citing = Note.objects.create(
            date=TODAY - timedelta(days=7),
            body=f"À ranger\n# ASTERICS\n[jour]({TODAY}) [plus tard](2999-01-01)",
        )
        process_passages(self.citing)
        # Des titres répétés : regroupement proposé (#315).
        self.repeated = Note.objects.create(
            date=TODAY - timedelta(days=14),
            body=(
                "# PDS1\n## x\n- [ ] a\n# ASTERICS\n# PDS1\n## x\nsuite\n"
                "# ASTERICS\n::: {.metadata}\ntags: [suivi]\n:::\nb"
            ),
        )
        process_passages(self.repeated)
        PendingProjectRename.objects.create(
            note=self.citing, old_name="PDS1", new_name="ASTERICS"
        )
        # Après les notes, dont l'enregistrement oublie les niveaux inutilisés.
        # Niveau inutilisé avec un sous-niveau : bouton de suppression actif (#299).
        section_for(project, ["Inutilisé", "Sous-niveau"])
        # Le même nom ailleurs (#376) et un niveau frère à réunir (#373, #374).
        section_for(other, ["reunion"])
        section_for(project, ["Réunions"])
        self.parent = Task.objects.create(
            title="Parent",
            project=project,
            section=Section.objects.get(name="Réunion"),
            due_date=TODAY,
            description="Première ligne\nSeconde ligne",
        )
        self.parent.tags.add(Tag.objects.get_or_create(name="urgent")[0])
        # Tâche dont la ligne a disparu de la note : seconde section du bilan (#240).
        Task.objects.create(
            title="Ligne retirée",
            project=project,
            created_from_note=True,
            note_date=TODAY,
            note_line_text="Ligne retirée",
            note_state=Task.NoteState.TO_REVIEW,
        )
        # Tâche écartée : section « Écartées » de la liste (#290).
        Task.objects.create(
            title="Écartée",
            project=project,
            created_from_note=True,
            note_date=TODAY,
            note_line_text="Écartée",
            note_state=Task.NoteState.DISMISSED,
        )
        # Sous-tâche incohérente : autre projet, échéance après le parent.
        Task.objects.create(
            title="Enfant",
            project=other,
            parent=self.parent,
            due_date=TODAY + timedelta(days=5),
            progress=40,
        )

    def pages(self) -> dict[str, str]:
        parent, note = self.parent.pk, self.note.date
        project = Project.objects.get(name="ASTERICS")
        section = Section.objects.get(project=project, name="Réunion")
        rename = reverse("core:section_rename", args=[project.pk, section.pk])
        return {
            "accueil": reverse("core:index"),
            "semaine": reverse("core:week_current"),
            "projets": reverse("core:projects"),
            "projet": reverse("core:project_detail", args=[project.pk]),
            "projet_niveau": (
                reverse("core:project_detail", args=[project.pk])
                + f"?path={section.pk}&group=path&order=asc&state=all"
            ),
            "projet_renommer": reverse("core:project_rename", args=[project.pk]),
            "projet_renommer_bilan": (
                reverse("core:project_rename", args=[project.pk]) + "?name=Alpha"
            ),
            "projet_nouveau": reverse("core:project_create"),
            "chemins": reverse("core:project_paths", args=[project.pk]),
            "chemin_renommer": rename,
            "chemin_bilan": f"{rename}?name=Rencontre",
            "chemin_nom_refuse": f"{rename}?name=Réunion",
            "chemin_reunion": f"{rename}?name=Réunions",
            "notes_accueil": reverse("note_taking:index"),
            "notes_liste": reverse("note_taking:notes_list"),
            "notes_liste_filtres": (
                reverse("note_taking:notes_list")
                + "?sort=date&project=ASTERICS&project=PDS1&date_from=2000-01-01"
            ),
            "note": reverse("note_taking:note_detail", args=[note]),
            "note_qui_cite": reverse(
                "note_taking:note_detail", args=[self.citing.date]
            ),
            "note_projet_renomme": reverse(
                "note_taking:project_rename_review", args=[self.citing.date]
            ),
            "note_titres_repetes": reverse(
                "note_taking:note_detail", args=[self.repeated.date]
            ),
            "note_regrouper": reverse(
                "note_taking:regroup_review", args=[self.repeated.date]
            ),
            "note_nouvelle": reverse("note_taking:new_note"),
            "note_modifier": reverse("note_taking:edit_note", args=[note]),
            "recherche": reverse("note_taking:notes_search"),
            "recherche_resultats": reverse("note_taking:notes_search") + "?q=point",
            "recherche_document": (
                reverse("note_taking:notes_search")
                + "?q=projet:ASTERICS&view=document&group=path"
            ),
            # Triée, par date, avec un niveau compris dans un projet coché (#430, #433).
            "recherche_document_par_date": (
                reverse("note_taking:notes_search")
                + f"?projects={project.pk}&subjects={section.pk}"
                + "&view=document&group=date&sort=oldest"
            ),
            "recherche_triee": (
                reverse("note_taking:notes_search") + "?q=point&sort=oldest"
            ),
            "recherche_filtres_seuls": (
                reverse("note_taking:notes_search") + "?q=projet:ASTERICS"
            ),
            "recherche_document_vide": (
                reverse("note_taking:notes_search") + "?q=introuvable&view=document"
            ),
            "images": reverse("note_taking:images_list"),
            "image": reverse("note_taking:image_detail", args=[self.image.pk]),
            "taches_accueil": reverse("todolist:index"),
            "taches_liste": reverse("todolist:task_list"),
            "taches_liste_filtres": (
                reverse("todolist:task_list")
                + "?state=all&title=e&sort=-due&project=ASTERICS&project=PDS1"
            ),
            "taches_liste_ecartees": reverse("todolist:task_list") + "?state=dismissed",
            "tache": reverse("todolist:task_detail", args=[parent]),
            "tache_nouvelle": reverse("todolist:task_create"),
            "tache_modifier": reverse("todolist:task_edit", args=[parent]),
            "taches_bilan": self.note.follow_ups[0].url,
        }

    def test_pages_valides(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, url in self.pages().items():
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, url)
                path = Path(directory) / f"{name}.html"
                path.write_bytes(response.content)
                paths.append(path)
            # L'éditeur qui refuse d'écraser la note (#386, #468) : réponse à un envoi,
            # avec les différences de la version enregistrée entre-temps (#471).
            response = self.client.post(
                reverse("note_taking:edit_note", args=[self.note.date]),
                {
                    "date": self.note.date,
                    "body": "x",
                    "version": "2020-01-01T00:00Z",
                    "original": NOTE_BODY.replace(
                        "## Réunion\n", "## Réunion\nretirée\n"
                    ),
                },
            )
            self.assertEqual(response.status_code, 409)
            path = Path(directory) / "note_conflit.html"
            path.write_bytes(response.content)
            paths.append(path)

            errors = html_validator.validate(paths)

        self.assertEqual(errors, [], "\n" + "\n".join(errors))


@unittest.skipUnless(
    html_validator.is_available(),
    "validateur HTML absent : python manage.py install_validator (Java requis)",
)
class DebugPagesValidationTests(DebugUrlsTestCase):
    """Les pages réservées au mode DEBUG (#235), dont la galerie des alertes (#156)."""

    def test_pages_de_debug_valides(self):
        pages = {
            "galerie_des_alertes": reverse("core:alerts_gallery"),
            "analyse_json_choix": reverse("note_taking:debug_note_json"),
        }
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, url in pages.items():
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, url)
                path = Path(directory) / f"{name}.html"
                path.write_bytes(response.content)
                paths.append(path)

            errors = html_validator.validate(paths)

        self.assertEqual(errors, [], "\n" + "\n".join(errors))
