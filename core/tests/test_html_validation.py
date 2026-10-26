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
from core.models import Project, Subject, Tag
from images.models import Image
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo

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

```python
print("<b>")
```

- Sous-liste
  - à 2 espaces
- [ ] Case vide
- [x] Case cochée

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

### TODO
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
        process_note_parts(self.note)
        self.parent = Todo.objects.create(
            title="Parent",
            project=project,
            subject=Subject.objects.get(name="Réunion"),
            due_date=TODAY,
            description="Première ligne\nSeconde ligne",
        )
        self.parent.tags.add(Tag.objects.get_or_create(name="urgent")[0])
        # Sous-tâche incohérente : autre projet, échéance après le parent.
        Todo.objects.create(
            title="Enfant",
            project=other,
            parent=self.parent,
            due_date=TODAY + timedelta(days=5),
            progress=40,
        )

    def pages(self) -> dict[str, str]:
        parent, note = self.parent.pk, self.note.pk
        return {
            "accueil": reverse("core:index"),
            "projets": reverse("core:projects"),
            "projet_nouveau": reverse("core:project_create"),
            "notes_accueil": reverse("note_taking:index"),
            "notes_liste": reverse("note_taking:notes_list"),
            "note": reverse("note_taking:note_detail", args=[note]),
            "note_markdown": reverse("note_taking:note_md", args=[note]),
            "note_nouvelle": reverse("note_taking:new_note"),
            "note_modifier": reverse("note_taking:edit_note", args=[note]),
            "recherche": reverse("note_taking:notes_search"),
            "images": reverse("note_taking:images_list"),
            "image": reverse("note_taking:image_detail", args=[self.image.pk]),
            "taches_accueil": reverse("todolist:index"),
            "taches_liste": reverse("todolist:todo_list"),
            "tache": reverse("todolist:todo_detail", args=[parent]),
            "tache_nouvelle": reverse("todolist:todo_create"),
            "tache_modifier": reverse("todolist:todo_edit", args=[parent]),
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

            errors = html_validator.validate(paths)

        self.assertEqual(errors, [], "\n" + "\n".join(errors))
