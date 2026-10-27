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


class NoteListTestCase(TestCase):
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


class NoteListTableTests(NoteListTestCase):
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
        # Une pastille retirable par projet, avec sa couleur.
        self.assertRegex(html, r"Projet :\s*<span class=\"inline-flex[^>]*>.*?Alpha")
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


class MultiProjectFilterTests(NoteListTestCase):
    """Le filtre par projet : plusieurs projets cochés, réunis par « ou »."""

    def panel(self, **params) -> str:
        html = self.get(**params).content.decode()
        return html[html.index('id="filters-projects"') :].split("</form>")[0]

    def test_zone_des_projets_repliable_comme_un_details_natif(self):
        panel = self.panel()

        self.assertIn("<details", panel)
        self.assertRegex(
            panel,
            r"<summary[^>]*>\s*Projets \(<span data-choice-count>0</span> sur 3\)",
        )

    def test_repliee_quand_aucun_projet_n_est_coche(self):
        self.assertRegex(self.panel(), r"<details data-choice-details>")

    def test_ouverte_d_office_quand_un_projet_est_coche(self):
        panel = self.panel(project="Alpha")

        self.assertRegex(panel, r"<details data-choice-details open>")

    def test_le_resume_compte_les_projets_coches(self):
        panel = self.panel(project=["Alpha", "Gamma"])

        self.assertRegex(panel, r"Projets \(<span data-choice-count>2</span> sur 3\)")

    def test_toutes_les_cases_restent_dans_le_details_sans_javascript(self):
        panel = self.panel()
        details = panel[panel.index("<details") : panel.index("</details>")]

        self.assertEqual(details.count('type="checkbox" name="project"'), 3)

    def test_la_recherche_est_hors_du_details_donc_toujours_visible(self):
        panel = self.panel()

        self.assertLess(panel.index("data-choice-search-box"), panel.index("<details"))

    def test_aucune_barre_de_defilement_dans_le_panneau(self):
        panel = self.panel()

        self.assertNotIn("overflow-y-auto", panel)
        self.assertNotIn("overflow-auto", panel)
        self.assertNotIn("max-h-", panel)

    def test_le_champ_de_recherche_s_aligne_et_son_contour_n_est_pas_rogne(self):
        panel = self.panel()
        box = panel[panel.index("data-choice-search-box") :].split(">")[0]

        # Pas de marge autour du champ (aligné sur les autres), et aucun
        # conteneur du panneau ne rogne le contour de focus.
        self.assertNotRegex(box, r'class="[^"]*p-')
        for clip in ("overflow-hidden", "overflow-auto", "overflow-y-auto"):
            self.assertNotIn(clip, panel)

    def test_union_des_projets_coches(self):
        response = self.get(project=["Alpha", "Gamma"])

        self.assertEqual(
            self.dates(response), ["2025-12-02", "2025-11-25", "2025-11-24"]
        )

    def test_aucun_projet_coche_les_montre_tous(self):
        self.assertEqual(len(self.dates(self.get(project=[]))), 4)
        self.assertEqual(len(self.dates(self.get(project=""))), 4)

    def test_note_des_deux_projets_coches_une_seule_fois(self):
        response = self.get(project=["Alpha", "Beta"])

        self.assertEqual(self.dates(response).count("2025-11-25"), 1)
        self.assertEqual(len(self.dates(response)), 3)

    def test_valeurs_inconnues_ignorees(self):
        response = self.get(project=["Gamma", "Inconnu"])

        self.assertEqual(self.dates(response), ["2025-12-02"])

    def test_cases_a_cocher_et_non_boutons_radio(self):
        html = self.get(project=["Alpha", "Gamma"]).content.decode()

        self.assertIn(
            '<input type="checkbox" name="project" value="Alpha" checked>', html
        )
        self.assertIn(
            '<input type="checkbox" name="project" value="Gamma" checked>', html
        )
        self.assertIn('<input type="checkbox" name="project" value="Beta">', html)
        self.assertNotIn('type="radio" name="project"', html)

    def test_pastille_a_cote_de_chaque_case(self):
        html = self.get().content.decode()
        panel = html[html.index('id="filters-projects"') :].split("</form>")[0]

        self.assertEqual(panel.count("size-2.5"), 3)

    def test_resume_une_pastille_retirable_par_projet(self):
        html = self.get(project=["Alpha", "Gamma"], sort="date").content.decode()

        self.assertEqual(html.count("(retirer ce filtre)"), 2)
        self.assertIn('href="?project=Gamma&amp;sort=date"', html)
        self.assertIn('href="?project=Alpha&amp;sort=date"', html)
        self.assertIn("Retirer tous les filtres", html)

    def test_recherche_dans_la_liste_cachee_sans_javascript(self):
        html = self.get().content.decode()
        panel = html[html.index('id="filters-projects"') :].split("</form>")[0]

        # Le champ ne se montre qu'avec le script ; sans lui toutes les cases sont là.
        self.assertRegex(panel, r"<div hidden data-choice-search-box[ >]")
        self.assertIn('placeholder="Chercher un projet"', panel)
        self.assertIn("autofocus", panel)
        self.assertEqual(panel.count("data-choice-item"), 3)
        self.assertNotRegex(panel, r"<label[^>]*data-choice-item[^>]*hidden")
        self.assertRegex(
            panel, r"<p hidden data-choice-empty[^>]*>Aucun projet ne correspond.</p>"
        )

    def test_script_de_recherche_charge_sur_la_page(self):
        response = self.get()

        self.assertContains(response, "core/table_filters.js")

    def test_les_projets_inconnus_des_notes_ne_sont_pas_proposes(self):
        Project.objects.create(name="Sans note", color="teal")

        self.assertNotContains(self.get(), 'value="Sans note"')
