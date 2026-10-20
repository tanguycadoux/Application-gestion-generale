"""Tests des composants d'interface partagés (balises de `core/templatetags/ui.py`)."""

import unittest

from django.template import Context, RequestContext, Template
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

PRIMARY = (
    "inline-flex items-center gap-2 my-[.4rem] rounded-[.8rem] p-[.6rem]"
    " font-semibold bg-primary-93 text-primary-40 hover:bg-primary-95"
)
DANGER = (
    "inline-flex items-center gap-2 my-[.4rem] rounded-[.8rem] p-[.6rem]"
    " font-semibold bg-alert-93 text-alert-40 hover:bg-alert-95"
)


def render(source: str, path: str = "/", **context) -> str:
    template = Template("{% load ui %}" + source)
    request = RequestFactory().get(path)
    return template.render(RequestContext(request, context))


class NavLinkTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_lien_de_navigation(self):
        html = render('{% nav_link "todolist:index" "Accueil" "home" %}')

        self.assertHTMLEqual(
            html,
            '<a class="flex items-center gap-2 rounded-2xl py-2 pr-3 pl-2'
            f' hover:bg-white" href="{reverse("todolist:index")}">'
            '<span class="material-symbols-rounded">home</span>'
            '<span class="font-medium">Accueil</span>'
            "</a>",
        )

    @unittest.expectedFailure
    def test_lien_actif_sur_la_page_courante(self):
        url = reverse("todolist:index")

        html = render('{% nav_link "todolist:index" "Accueil" "home" %}', path=url)

        self.assertIn("hover:bg-white bg-white", html)
        self.assertIn('aria-current="page"', html)


class ButtonTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_bouton_principal(self):
        html = render('{% button "Importer" %}')

        self.assertHTMLEqual(
            html, f'<button type="submit" class="{PRIMARY}">Importer</button>'
        )

    @unittest.expectedFailure
    def test_bouton_danger(self):
        html = render('{% button "Supprimer" variant="danger" %}')

        self.assertHTMLEqual(
            html, f'<button type="submit" class="{DANGER}">Supprimer</button>'
        )

    @unittest.expectedFailure
    def test_bouton_icone_seule(self):
        html = render('{% button "Enregistrer" icon="save" icon_only=True %}')

        self.assertHTMLEqual(
            html,
            f'<button type="submit" class="{PRIMARY}" aria-label="Enregistrer">'
            '<span class="material-symbols-rounded">save</span>'
            "</button>",
        )


class LinkButtonTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_lien_en_forme_de_bouton(self):
        html = render('{% link_button "/todo/" "Modifier" %}')

        self.assertHTMLEqual(html, f'<a class="{PRIMARY}" href="/todo/">Modifier</a>')

    @unittest.expectedFailure
    def test_lien_danger(self):
        html = render('{% link_button "/todo/" "Supprimer" variant="danger" %}')

        self.assertHTMLEqual(html, f'<a class="{DANGER}" href="/todo/">Supprimer</a>')


class IconLinkTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_lien_icone(self):
        html = render('{% icon_link "/edit/" "Modifier" "edit" %}')

        self.assertHTMLEqual(
            html,
            '<a class="inline-flex rounded-2xl p-2 hover:bg-slate-200"'
            ' href="/edit/" aria-label="Modifier">'
            '<span class="material-symbols-rounded">edit</span>'
            "</a>",
        )

    @unittest.expectedFailure
    def test_lien_icone_danger(self):
        html = render(
            '{% icon_link "/delete/" "Supprimer" "delete" variant="danger" %}'
        )

        self.assertIn('class="inline-flex rounded-2xl p-2 hover:bg-red-200"', html)


class TagListTests(SimpleTestCase):
    TAG = (
        "rounded-2xl border border-[oklch(80%_0_0)] bg-[oklch(92%_0_0)]"
        " px-[.4rem] py-[.1rem] text-[.8rem] font-semibold"
    )

    @unittest.expectedFailure
    def test_liste_de_tags(self):
        html = render("{% tag_list tags %}", tags=["a", "<b>"])

        self.assertHTMLEqual(
            html,
            '<ul class="m-0 flex h-fit list-none gap-[.4rem] p-0">'
            f'<li class="{self.TAG}">a</li>'
            f'<li class="{self.TAG}">&lt;b&gt;</li>'
            "</ul>",
        )

    @unittest.expectedFailure
    def test_liste_vide(self):
        html = render("{% tag_list tags %}", tags=[])

        self.assertHTMLEqual(html, "")


class LoadUiLibraryTests(SimpleTestCase):
    @unittest.expectedFailure
    def test_bibliotheque_chargee_sans_requete(self):
        """Les composants hors navigation n'ont pas besoin de la requête."""
        html = Template('{% load ui %}{% button "OK" %}').render(Context())

        self.assertIn(">OK</button>", html)
