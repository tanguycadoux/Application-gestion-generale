"""Recherches enregistrées (#203) : une requête gardée sous un nom."""

from django.contrib.messages import get_messages
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from note_taking.exceptions import SavedSearchError
from note_taking.models import SavedSearch
from note_taking.saved_searches import rename_search, save_search, search_url

SEARCH = reverse("note_taking:notes_search")
CREATE = reverse("note_taking:saved_search_create")


def messages_of(response) -> list[tuple[str, str]]:
    return [(m.level_tag, m.message) for m in get_messages(response.wsgi_request)]


class SaveSearchTests(TestCase):
    def test_enregistre_sous_un_nom(self):
        saved = save_search("  Urgent chez Alpha ", "tag:urgent projet:Alpha")

        self.assertEqual(saved.name, "Urgent chez Alpha")
        self.assertEqual(saved.q, "tag:urgent projet:Alpha")
        self.assertEqual(SavedSearch.objects.count(), 1)

    def test_la_requete_est_gardee_telle_quelle(self):
        saved = save_search("A", ' "phrase exacte"  -mot ')

        self.assertEqual(saved.q, '"phrase exacte"  -mot')

    def test_nom_vide(self):
        for name in ["", "   "]:
            with self.subTest(name=name):
                with self.assertRaisesMessage(SavedSearchError, "nom"):
                    save_search(name, "banc")

    def test_nom_trop_long(self):
        with self.assertRaisesMessage(SavedSearchError, "100"):
            save_search("x" * 101, "banc")

    def test_requete_vide(self):
        for q in ["", "   "]:
            with self.subTest(q=q):
                with self.assertRaisesMessage(SavedSearchError, "vide"):
                    save_search("A", q)

    def test_meme_nom_refuse_sans_casse_ni_accents(self):
        save_search("Réunion", "banc")

        for name in ["Réunion", "réunion", "REUNION"]:
            with self.subTest(name=name):
                with self.assertRaisesMessage(SavedSearchError, "existe déjà"):
                    save_search(name, "autre")

        self.assertEqual(SavedSearch.objects.count(), 1)

    def test_le_nom_est_unique_en_base(self):
        SavedSearch.objects.create(name="A", q="x")

        with self.assertRaises(IntegrityError), transaction.atomic():
            SavedSearch.objects.create(name="A", q="y")

    def test_renommer(self):
        saved = save_search("Ancien", "banc")

        rename_search(saved, " Nouveau ")

        saved.refresh_from_db()
        self.assertEqual(saved.name, "Nouveau")
        self.assertEqual(saved.q, "banc")

    def test_renommer_en_changeant_la_casse(self):
        saved = save_search("réunion", "banc")

        rename_search(saved, "Réunion")

        saved.refresh_from_db()
        self.assertEqual(saved.name, "Réunion")

    def test_renommer_vers_un_nom_pris(self):
        save_search("A", "x")
        other = save_search("B", "y")

        with self.assertRaisesMessage(SavedSearchError, "existe déjà"):
            rename_search(other, "a")

        other.refresh_from_db()
        self.assertEqual(other.name, "B")

    def test_adresse_de_la_recherche(self):
        saved = save_search("A", 'projet:"Mon projet" é&=')

        self.assertEqual(
            search_url(saved),
            SEARCH + "?q=projet%3A%22Mon+projet%22+%C3%A9%26%3D",
        )


class SavedSearchViewTests(TestCase):
    def test_creer(self):
        response = self.client.post(CREATE, {"name": "Urgent", "q": "tag:urgent"})

        self.assertRedirects(
            response, SEARCH + "?q=tag%3Aurgent", fetch_redirect_response=False
        )
        self.assertEqual(SavedSearch.objects.get().name, "Urgent")
        self.assertEqual(messages_of(response)[0][0], "success")
        self.assertIn("Urgent", messages_of(response)[0][1])

    def test_creer_avec_un_nom_pris_ne_plante_pas(self):
        SavedSearch.objects.create(name="Urgent", q="a")

        response = self.client.post(CREATE, {"name": "urgent", "q": "tag:urgent"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SavedSearch.objects.count(), 1)
        self.assertEqual(messages_of(response)[0][0], "error")
        self.assertIn("existe déjà", messages_of(response)[0][1])

    def test_creer_sans_nom_garde_la_requete_dans_l_adresse(self):
        response = self.client.post(CREATE, {"name": " ", "q": "tag:urgent"})

        self.assertRedirects(
            response, SEARCH + "?q=tag%3Aurgent", fetch_redirect_response=False
        )
        self.assertEqual(SavedSearch.objects.count(), 0)
        self.assertEqual(messages_of(response)[0][0], "error")

    def test_creer_refuse_le_get(self):
        self.assertEqual(self.client.get(CREATE).status_code, 405)

    def test_renommer(self):
        saved = SavedSearch.objects.create(name="Ancien", q="banc")
        url = reverse("note_taking:saved_search_rename", args=[saved.pk])

        response = self.client.post(url + "?q=banc", {"name": "Nouveau"})

        self.assertRedirects(
            response, SEARCH + "?q=banc", fetch_redirect_response=False
        )
        saved.refresh_from_db()
        self.assertEqual(saved.name, "Nouveau")
        self.assertEqual(messages_of(response)[0][0], "success")

    def test_renommer_vers_un_nom_pris(self):
        SavedSearch.objects.create(name="A", q="x")
        saved = SavedSearch.objects.create(name="B", q="y")
        url = reverse("note_taking:saved_search_rename", args=[saved.pk])

        response = self.client.post(url, {"name": "a"})

        self.assertEqual(response.status_code, 302)
        saved.refresh_from_db()
        self.assertEqual(saved.name, "B")
        self.assertEqual(messages_of(response)[0][0], "error")

    def test_renommer_une_recherche_inconnue(self):
        url = reverse("note_taking:saved_search_rename", args=[999])

        self.assertEqual(self.client.post(url, {"name": "A"}).status_code, 404)

    def test_supprimer(self):
        saved = SavedSearch.objects.create(name="A", q="banc")
        url = reverse("note_taking:saved_search_delete", args=[saved.pk])

        response = self.client.post(url + "?q=autre", {})

        self.assertRedirects(
            response, SEARCH + "?q=autre", fetch_redirect_response=False
        )
        self.assertFalse(SavedSearch.objects.exists())
        self.assertEqual(messages_of(response)[0][0], "success")

    def test_supprimer_refuse_le_get_et_ignore_l_inconnue(self):
        saved = SavedSearch.objects.create(name="A", q="banc")

        self.assertEqual(
            self.client.get(
                reverse("note_taking:saved_search_delete", args=[saved.pk])
            ).status_code,
            405,
        )
        self.assertEqual(
            self.client.post(
                reverse("note_taking:saved_search_delete", args=[999])
            ).status_code,
            404,
        )
        self.assertTrue(SavedSearch.objects.exists())

    def test_adresse_de_retour_hors_du_site_ignoree(self):
        saved = SavedSearch.objects.create(name="A", q="banc")
        url = reverse("note_taking:saved_search_delete", args=[saved.pk])

        response = self.client.post(url + "?q=a%0D%0ALocation:+http://x", {})

        self.assertTrue(response["Location"].startswith(SEARCH))
        self.assertNotIn("\n", response["Location"])


class SavedSearchPageTests(TestCase):
    def test_liste_triee_avec_un_lien_par_recherche(self):
        SavedSearch.objects.create(name="zèbre", q="b c")
        SavedSearch.objects.create(name="Alpha", q='projet:"A B" é')

        html = self.client.get(SEARCH).content.decode()

        self.assertIn("Recherches enregistrées", html)
        self.assertLess(html.index("Alpha"), html.index("zèbre"))
        self.assertIn(f'href="{SEARCH}?q=projet%3A%22A+B%22+%C3%A9"', html)
        self.assertIn(f'href="{SEARCH}?q=b+c"', html)

    def test_sans_recherche_enregistree(self):
        response = self.client.get(SEARCH)

        self.assertContains(response, "Aucune recherche enregistrée.")

    def test_formulaire_prerempli_par_la_requete(self):
        response = self.client.get(SEARCH, {"q": "tag:urgent"})

        self.assertContains(response, f'action="{CREATE}"')
        self.assertContains(response, 'name="q" value="tag:urgent"')
        self.assertContains(response, 'name="name" value="tag:urgent"')

    def test_pas_de_formulaire_sans_requete(self):
        response = self.client.get(SEARCH)

        self.assertNotContains(response, f'action="{CREATE}"')
        self.assertContains(response, "Lancer une recherche")

    def test_la_recherche_courante_est_marquee(self):
        SavedSearch.objects.create(name="Alpha", q="banc")
        SavedSearch.objects.create(name="Beta", q="autre")

        html = self.client.get(SEARCH, {"q": "banc"}).content.decode()

        self.assertEqual(html.count('aria-current="true"'), 1)
        self.assertLess(html.index('aria-current="true"'), html.index("Beta"))

    def test_suppression_confirmee_par_une_popover(self):
        saved = SavedSearch.objects.create(name="Alpha", q="banc")

        response = self.client.get(SEARCH, {"q": "banc"})

        delete = reverse("note_taking:saved_search_delete", args=[saved.pk])
        self.assertContains(response, f'action="{delete}?q=banc"')
        self.assertContains(response, f'id="delete-saved-search-{saved.pk}"')
        self.assertContains(response, "popover")

    def test_renommer_est_un_formulaire(self):
        saved = SavedSearch.objects.create(name="Alpha", q="banc")

        response = self.client.get(SEARCH, {"q": "banc"})

        rename = reverse("note_taking:saved_search_rename", args=[saved.pk])
        self.assertContains(response, f'action="{rename}?q=banc"')

    def test_les_noms_sont_echappes(self):
        SavedSearch.objects.create(name="<b>x</b>", q="<i>y</i>")

        html = self.client.get(SEARCH).content.decode()

        self.assertNotIn("<b>x</b>", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)

    def test_aussi_dans_les_resultats_htmx(self):
        """Les résultats remplacés par htmx ne contiennent pas la liste."""
        SavedSearch.objects.create(name="Alpha", q="banc")

        response = self.client.get(
            SEARCH, {"q": "banc"}, headers={"HX-Request": "true"}
        )

        self.assertNotContains(response, "Recherches enregistrées")
