"""Le tableau des notes : tri et filtres dans l'URL, par les composants communs (#178)."""

from django.test import TestCase
from django.urls import reverse

from core.models import Project
from core.tables import Sort
from note_taking.models import Note
from note_taking.services import process_note_parts


def make_note(day: str, *projects: str) -> Note:
    body = "\n".join(f"# {name}\ntexte" for name in projects) or "texte"
    note = Note.objects.create(date=day, body=body)
    process_note_parts(note)
    return note


class NoteListTableTests(TestCase):
    def setUp(self):
        make_note("2025-11-24", "Alpha")
        make_note("2025-11-25", "Beta", "Alpha")
        make_note("2025-11-26", "Beta")
        make_note("2025-12-02", "Gamma")
        self.url = reverse("note_taking:notes_list")

    def get(self, **params):
        return self.client.get(self.url, params)

    def dates(self, response) -> list[str]:
        return [str(note.date) for note in response.context["notes"]]

    def test_tri_par_defaut_du_plus_recent_au_plus_ancien(self):
        response = self.get()

        self.assertEqual(
            self.dates(response),
            ["2025-12-02", "2025-11-26", "2025-11-25", "2025-11-24"],
        )
        self.assertEqual(response.context["sort"], Sort("date", True))

    def test_tri_croissant_et_decroissant(self):
        self.assertEqual(self.dates(self.get(sort="date"))[0], "2025-11-24")
        self.assertEqual(self.dates(self.get(sort="-date"))[0], "2025-12-02")

    def test_tri_inconnu_revient_au_tri_par_defaut(self):
        for sort in ("foo", "body", "-foo", ""):
            with self.subTest(sort=sort):
                response = self.get(sort=sort)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["sort"], Sort("date", True))
                self.assertEqual(self.dates(response)[0], "2025-12-02")

    def test_en_tete_date_est_un_lien_de_tri_avec_aria_sort(self):
        html = self.get().content.decode()

        self.assertIn('aria-sort="descending"', html)
        self.assertIn('href="?sort=date"', html)
        self.assertIn("Date", html)

    def test_en_tete_apres_un_tri_croissant(self):
        html = self.get(sort="date").content.decode()

        self.assertIn('aria-sort="ascending"', html)
        self.assertIn('href="?sort=-date"', html)

    def test_filtre_par_projet(self):
        response = self.get(project="Alpha")

        self.assertEqual(self.dates(response), ["2025-11-25", "2025-11-24"])

    def test_note_a_deux_parties_du_meme_projet_une_seule_fois(self):
        make_note("2025-12-03", "Alpha", "Beta", "Alpha")

        response = self.get(project="Alpha")

        self.assertEqual(self.dates(response).count("2025-12-03"), 1)

    def test_les_projets_d_une_note_filtree_restent_tous_affiches(self):
        html = self.get(project="Alpha").content.decode()

        # La note du 25 appartient à Beta aussi : le filtre ne cache pas ses projets.
        self.assertIn("Beta", html)

    def test_projet_inconnu_ignore(self):
        response = self.get(project="Inconnu")

        self.assertEqual(len(self.dates(response)), 4)

    def test_filtre_par_dates(self):
        response = self.get(date_from="2025-11-25", date_to="2025-11-26")

        self.assertEqual(self.dates(response), ["2025-11-26", "2025-11-25"])

    def test_filtre_depuis_une_date(self):
        response = self.get(date_from="2025-12-01")

        self.assertEqual(self.dates(response), ["2025-12-02"])

    def test_date_mal_ecrite_signalee_et_liste_complete(self):
        response = self.get(date_from="demain")

        self.assertEqual(len(self.dates(response)), 4)
        self.assertContains(response, "pas une date")

    def test_filtres_et_tri_se_combinent(self):
        response = self.get(project="Beta", sort="date", date_from="2025-11-26")

        self.assertEqual(self.dates(response), ["2025-11-26"])

    def test_filtre_sans_resultat_laisse_le_tableau_pour_changer_les_filtres(self):
        response = self.get(project="Gamma", date_to="2025-11-30")

        self.assertEqual(self.dates(response), [])
        self.assertContains(response, 'id="filters-date"')
        self.assertContains(response, "Aucune note ne répond aux filtres")

    def test_resume_des_filtres_actifs_et_retrait(self):
        html = self.get(project="Alpha", sort="date").content.decode()

        self.assertIn('aria-label="Filtres actifs"', html)
        self.assertIn("Projet : Alpha", html)
        self.assertIn('href="?sort=date"', html)

    def test_entonnoirs_dans_les_en_tetes(self):
        html = self.get().content.decode()

        self.assertIn('popovertarget="filters-date"', html)
        self.assertIn('popovertarget="filters-projects"', html)
        self.assertIn('<div popover id="filters-projects"', html)

    def test_entonnoir_d_un_filtre_actif_est_bleu_et_annonce(self):
        html = self.get(project="Alpha").content.decode()

        self.assertIn("filtre actif", html)

    def test_panneau_des_projets_ne_propose_que_les_projets_des_notes(self):
        Project.objects.create(name="Sans note", color="teal")

        response = self.get()

        self.assertContains(response, 'value="Alpha"')
        self.assertContains(response, 'value="Gamma"')
        self.assertNotContains(response, "Sans note")

    def test_panneau_reprend_le_tri_en_champ_cache(self):
        html = self.get(sort="date").content.decode()

        self.assertIn('<input type="hidden" name="sort" value="date">', html)

    def test_export_compte_toutes_les_notes_meme_filtrees(self):
        response = self.get(project="Alpha")

        self.assertContains(response, "Exporter les 4 notes")

    def test_plus_de_popover_provisoire(self):
        html = self.get().content.decode()

        self.assertNotIn("table-column-head", html)
        self.assertNotIn("table.js", html)
