"""Cycle de vie des tâches issues des notes (#240).

Une tâche générée est identifiée par la date de la note, le chemin des titres
tels qu'écrits (sans `TODO`) et le chemin de sa ligne.
"""

import re

from django.test import TestCase
from django.urls import reverse

from core.forms import section_path_text
from core.models import Project
from note_taking.models import Note
from note_taking.services import process_note_parts
from todolist.models import Todo


class LifecycleTestCase(TestCase):
    def save_note(self, body: str, date: str = "2025-11-24") -> Note:
        note, _ = Note.objects.update_or_create(date=date, defaults={"body": body})
        process_note_parts(note)
        return note

    def titles(self) -> list[str]:
        return list(Todo.objects.order_by("pk").values_list("title", flat=True))


class IdentityTests(LifecycleTestCase):
    def test_meme_ligne_sous_deux_sujets(self):
        self.save_note("# P\n## A\n### TODO\n- Tâche\n## B\n### TODO\n- Tâche")

        self.assertEqual(self.titles(), ["Tâche", "Tâche"])

    def test_meme_ligne_sous_deux_parents(self):
        self.save_note("# P\n### TODO\n- A\n  - Relire\n- B\n  - Relire")

        relire = Todo.objects.filter(title="Relire").select_related("parent")
        self.assertEqual(sorted(todo.parent.title for todo in relire), ["A", "B"])

    def test_chemin_retenu(self):
        self.save_note("# P\n## S\n### TODO\n- A\n  - B")

        self.assertEqual(Todo.objects.get(title="B").note_path, "P › S › A")

    def test_reenregistree_sans_doublon(self):
        body = "# P\n## A\n### TODO\n- Tâche\n  - Sous-tâche"
        self.save_note(body)
        self.save_note(body)

        self.assertEqual(self.titles(), ["Tâche", "Sous-tâche"])

    def test_tache_d_avant_reprise_sans_doublon(self):
        """Une tâche créée avant #240, sans chemin, est reprise par sa ligne."""
        Todo.objects.create(
            title="Renommée",
            project=Project.objects.create(name="P"),
            created_from_note=True,
            note_part_date="2025-11-24",
            note_part_text="Tâche",
        )

        self.save_note("# P\n## A\n### TODO\n- Tâche")

        todo = Todo.objects.get()
        self.assertEqual((todo.title, todo.note_path), ("Renommée", "P › A"))


def review_url(note_date: str = "2025-11-24") -> str:
    return reverse("todolist:note_review", args=[note_date])


def review_data(new=(), gone=()) -> dict:
    """Données du bilan : `new`, les tâches dont la ligne existe ; `gone`, des
    couples (tâche dont la ligne a disparu, action, tâche de remplacement)."""
    data = {
        "new-TOTAL_FORMS": str(len(new)),
        "new-INITIAL_FORMS": str(len(new)),
        "gone-TOTAL_FORMS": str(len(gone)),
        "gone-INITIAL_FORMS": str(len(gone)),
    }
    for i, todo in enumerate(new):
        data |= {
            f"new-{i}-id": todo.pk,
            f"new-{i}-due_date": "",
            f"new-{i}-priority": todo.priority,
            f"new-{i}-project": todo.project_id,
            f"new-{i}-section_path": section_path_text(todo.section),
        }
    for i, (todo, action, replacement) in enumerate(gone):
        data |= {
            f"gone-{i}-id": todo.pk,
            f"gone-{i}-action": action,
            f"gone-{i}-replacement": replacement.pk if replacement else "",
        }
    return data


class ToReviewTests(LifecycleTestCase):
    BODY = "# P\n### TODO\n- A\n- B"

    def edit(self, note: Note, body: str):
        return self.client.post(
            reverse("note_taking:edit_note", args=[note.pk]),
            {"date": "2025-11-24", "body": body},
        )

    def test_tache_creee_a_revoir(self):
        self.save_note(self.BODY)

        self.assertEqual(
            set(Todo.objects.values_list("note_state", flat=True)),
            {Todo.NoteState.TO_REVIEW},
        )

    def test_tache_saisie_a_la_main_sans_etat(self):
        todo = Todo.objects.create(title="T", project=Project.objects.create(name="P"))

        self.assertEqual(todo.note_state, "")

    def test_plus_tard_le_bilan_revient(self):
        note = self.save_note(self.BODY)

        response = self.edit(note, self.BODY + "\n\n# Q\ntexte")

        self.assertRedirects(response, review_url())

    def test_bilan_enregistre_ne_revient_pas(self):
        note = self.save_note(self.BODY)
        self.client.post(review_url(), review_data(new=Todo.objects.order_by("pk")))

        response = self.edit(note, self.BODY + "\n\n# Q\ntexte")

        self.assertRedirects(
            response, reverse("note_taking:note_detail", args=[note.pk])
        )


class GoneLineTests(LifecycleTestCase):
    def prepare(self):
        self.note = self.save_note("# P\n### TODO\n- A\n- B")
        Todo.objects.update(note_state=Todo.NoteState.REVIEWED)
        self.a, self.b = Todo.objects.order_by("pk")

    def state(self, todo: Todo) -> str:
        return Todo.all_objects.get(pk=todo.pk).note_state

    def test_ligne_retiree_a_revoir(self):
        self.prepare()
        self.save_note("# P\n### TODO\n- A")

        self.assertEqual(self.state(self.b), Todo.NoteState.TO_REVIEW)
        self.assertEqual(self.state(self.a), Todo.NoteState.REVIEWED)

    def test_bilan_separe_nouvelles_et_disparues(self):
        self.prepare()
        self.save_note("# P\n### TODO\n- A\n- B modifiée")

        response = self.client.get(review_url())

        new = [form.instance.title for form in response.context["new_formset"]]
        gone = [form.instance.title for form in response.context["gone_formset"]]
        self.assertEqual((new, gone), (["B modifiée"], ["B"]))

    def test_nouvelle_ligne_visible_seulement_pour_remplacer(self):
        """Le choix de la nouvelle ligne ne s'affiche qu'avec « La remplacer
        par », sans JavaScript : la cellule suit l'action de sa rangée."""
        self.prepare()
        self.save_note("# P\n### TODO\n- A\n- B modifiée")

        html = self.client.get(review_url()).content.decode()

        row = re.search(r'<tr class="group[^"]*">.*?</tr>', html, re.DOTALL)
        assert row is not None
        cell = re.search(
            r'<td class="([^"]*)">(?:(?!</td>).)*-replacement"', row.group(), re.DOTALL
        )
        assert cell is not None
        self.assertIn(
            "invisible group-has-[option[value=replace]:checked]:visible",
            cell.group(1),
        )

    def test_garder(self):
        self.prepare()
        self.save_note("# P\n### TODO\n- A")

        self.client.post(review_url(), review_data(gone=[(self.b, "keep", None)]))
        self.save_note("# P\n### TODO\n- A")

        self.assertEqual(self.state(self.b), Todo.NoteState.DETACHED)

    def test_ecarter(self):
        self.prepare()
        self.save_note("# P\n### TODO\n- A")

        self.client.post(review_url(), review_data(gone=[(self.b, "dismiss", None)]))

        self.assertEqual(self.state(self.b), Todo.NoteState.DISMISSED)
        self.assertFalse(Todo.objects.filter(pk=self.b.pk).exists())

    def test_ecartee_pas_recreee(self):
        self.prepare()
        self.save_note("# P\n### TODO\n- A")
        self.client.post(review_url(), review_data(gone=[(self.b, "dismiss", None)]))

        self.save_note("# P\n### TODO\n- A\n- B")

        self.assertEqual(Todo.all_objects.filter(title="B").count(), 1)
        self.assertEqual(self.state(self.b), Todo.NoteState.DISMISSED)

    def replace_b(self, body: str, new_title: str):
        self.save_note(body)
        new = Todo.objects.get(title=new_title)
        self.client.post(
            review_url(),
            review_data(
                new=Todo.objects.filter(note_state=Todo.NoteState.TO_REVIEW).exclude(
                    pk=self.b.pk
                ),
                gone=[(self.b, "replace", new)],
            ),
        )
        return new

    def test_remplacer_garde_avancement_et_echeance(self):
        self.prepare()
        Todo.objects.filter(pk=self.b.pk).update(progress=60, due_date="2025-12-01")

        new = self.replace_b("# P\n### TODO\n- A\n- B modifiée", "B modifiée")

        b = Todo.objects.get(pk=self.b.pk)
        self.assertEqual(
            (b.title, b.note_part_text, b.progress, str(b.due_date), b.note_state),
            ("B modifiée", "B modifiée", 60, "2025-12-01", Todo.NoteState.REVIEWED),
        )
        self.assertFalse(Todo.all_objects.filter(pk=new.pk).exists())

    def test_remplacer_garde_et_reprend_les_sous_taches(self):
        self.prepare()
        Todo.objects.create(title="Enfant", project=self.b.project, parent=self.b)
        body = "# P\n### TODO\n- A\n- B modifiée\n  - Sous-ligne"

        self.replace_b(body, "B modifiée")

        b = Todo.objects.get(pk=self.b.pk)
        self.assertEqual(
            sorted(b.children.values_list("title", flat=True)),
            ["Enfant", "Sous-ligne"],
        )
        self.save_note(body)
        self.assertEqual(Todo.objects.count(), 4)

    def test_remplacer_garde_un_titre_renomme(self):
        self.prepare()
        Todo.objects.filter(pk=self.b.pk).update(title="Renommée")
        self.save_note("# P\n### TODO\n- A\n- C")
        new = Todo.objects.get(title="C")

        self.client.post(
            review_url(),
            review_data(new=[new], gone=[(self.b, "replace", new)]),
        )

        self.assertEqual(Todo.objects.get(pk=self.b.pk).title, "Renommée")

    def test_remplacer_sans_tache_choisie(self):
        self.prepare()
        self.save_note("# P\n### TODO\n- A")

        response = self.client.post(
            review_url(), review_data(gone=[(self.b, "replace", None)])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.state(self.b), Todo.NoteState.TO_REVIEW)


class DeleteTests(LifecycleTestCase):
    def delete(self, todo: Todo):
        return self.client.post(reverse("todolist:todo_delete", args=[todo.pk]))

    def test_supprimer_une_tache_de_note_l_ecarte(self):
        self.save_note("# P\n### TODO\n- A")
        todo = Todo.objects.get()

        self.delete(todo)
        self.save_note("# P\n### TODO\n- A")

        self.assertFalse(Todo.objects.exists())
        self.assertEqual(Todo.all_objects.get().note_state, Todo.NoteState.DISMISSED)

    def test_supprimer_une_tache_saisie_a_la_main(self):
        todo = Todo.objects.create(title="T", project=Project.objects.create(name="P"))

        self.delete(todo)

        self.assertFalse(Todo.all_objects.exists())

    # Un arbre qui contient une tâche issue d'une note est écarté en entier, même
    # ses tâches saisies à la main : le rétablir le rend intact (#290).
    def test_parent_saisi_a_la_main_avec_enfant_de_note(self):
        self.save_note("# P\n### TODO\n- A")
        child = Todo.objects.get()
        parent = Todo.objects.create(title="Parent", project=child.project)
        Todo.objects.filter(pk=child.pk).update(parent=parent)

        self.delete(parent)

        self.assertFalse(Todo.objects.exists())
        child = Todo.all_objects.get(pk=child.pk)
        self.assertEqual(
            (child.note_state, child.parent_id), (Todo.NoteState.DISMISSED, parent.pk)
        )
        self.assertEqual(
            Todo.all_objects.get(pk=parent.pk).note_state, Todo.NoteState.DISMISSED
        )

    def test_enfant_saisi_a_la_main_ecarte_avec_sa_tache_de_note(self):
        self.save_note("# P\n### TODO\n- A")
        parent = Todo.objects.get()
        child = Todo.objects.create(
            title="Enfant", project=parent.project, parent=parent
        )

        self.delete(parent)

        self.assertFalse(Todo.objects.exists())
        self.assertEqual(
            Todo.all_objects.get(pk=child.pk).note_state, Todo.NoteState.DISMISSED
        )

    def test_tache_ecartee_portee_par_un_arbre_saisi_a_la_main(self):
        """Une tâche déjà écartée sous un arbre supprimé n'est pas emportée."""
        self.save_note("# P\n### TODO\n- A")
        child = Todo.objects.get()
        parent = Todo.objects.create(title="Parent", project=child.project)
        Todo.objects.filter(pk=child.pk).update(parent=parent)
        self.delete(child)

        self.delete(parent)

        self.assertFalse(Todo.all_objects.filter(pk=parent.pk).exists())
        self.assertIsNone(Todo.all_objects.get(pk=child.pk).parent_id)

    def test_sous_tache_ecartee_hors_de_l_avancement_du_parent(self):
        self.save_note("# P\n### TODO\n- A\n  - B\n  - C")
        b = Todo.objects.get(title="B")
        Todo.objects.filter(title="C").update(progress=100)
        b.progress = 0
        b.save()

        self.delete(b)

        self.assertEqual(Todo.objects.get(title="A").progress, 100)

    def test_projet_utilise_seulement_par_des_ecartees(self):
        self.save_note("# P\n### TODO\n- A")
        project = Todo.objects.get().project
        self.delete(Todo.objects.get())
        Note.objects.all().delete()

        self.client.post(reverse("core:project_delete", args=[project.pk]))

        self.assertFalse(Project.objects.filter(pk=project.pk).exists())
        self.assertFalse(Todo.all_objects.exists())
