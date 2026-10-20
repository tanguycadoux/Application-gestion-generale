"""Tests des composants d'interface partagés (balises de `core/templatetags/ui.py`)."""

from django.template import Context, RequestContext, Template
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

SHAPE = "inline-flex items-center gap-2 rounded-xl p-2 font-semibold"
PRIMARY = SHAPE + " bg-blue-100 text-blue-800 hover:bg-blue-50"
DANGER = SHAPE + " bg-red-100 text-red-800 hover:bg-red-50"
GHOST = SHAPE + " hover:bg-slate-200"
GHOST_DANGER = SHAPE + " text-red-800 hover:bg-red-100"


def render(source: str, path: str = "/", **context) -> str:
    template = Template("{% load ui %}" + source)
    request = RequestFactory().get(path)
    return template.render(RequestContext(request, context))


class NavLinkTests(SimpleTestCase):
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

    def test_lien_actif_sur_la_page_courante(self):
        url = reverse("todolist:index")

        html = render('{% nav_link "todolist:index" "Accueil" "home" %}', path=url)

        self.assertIn("hover:bg-white bg-white", html)
        self.assertIn('aria-current="page"', html)


class ButtonTests(SimpleTestCase):
    def test_bouton_principal(self):
        html = render('{% button "Importer" %}')

        self.assertHTMLEqual(
            html, f'<button type="submit" class="{PRIMARY}">Importer</button>'
        )

    def test_bouton_danger(self):
        html = render('{% button "Supprimer" variant="danger" %}')

        self.assertHTMLEqual(
            html, f'<button type="submit" class="{DANGER}">Supprimer</button>'
        )

    def test_bouton_icone_seule(self):
        html = render('{% button "Enregistrer" icon="save" icon_only=True %}')

        self.assertHTMLEqual(
            html,
            f'<button type="submit" class="{PRIMARY}" aria-label="Enregistrer">'
            '<span class="material-symbols-rounded">save</span>'
            "</button>",
        )

    def test_type_du_bouton(self):
        html = render('{% button "Annuler" type="reset" %}')

        self.assertIn('<button type="reset"', html)

    def test_lien_avec_href(self):
        html = render('{% button "Modifier" href="/todo/" type="reset" %}')

        self.assertHTMLEqual(html, f'<a class="{PRIMARY}" href="/todo/">Modifier</a>')

    def test_lien_danger(self):
        html = render('{% button "Supprimer" href="/todo/" variant="danger" %}')

        self.assertHTMLEqual(html, f'<a class="{DANGER}" href="/todo/">Supprimer</a>')

    def test_lien_icone_seule_discret(self):
        html = render(
            '{% button "Modifier" icon="edit" href="/edit/" variant="ghost"'
            " icon_only=True %}"
        )

        self.assertHTMLEqual(
            html,
            f'<a class="{GHOST}" href="/edit/" aria-label="Modifier">'
            '<span class="material-symbols-rounded">edit</span>'
            "</a>",
        )

    def test_variante_discrete_danger(self):
        html = render('{% button "Supprimer" variant="ghost-danger" %}')

        self.assertIn(f'class="{GHOST_DANGER}"', html)

    def test_bouton_desactive(self):
        html = render('{% button "Supprimer" variant="danger" disabled=True %}')

        self.assertIn(" disabled", html)
        self.assertIn("cursor-not-allowed", html)
        self.assertIn("opacity-50", html)
        self.assertNotIn("hover:", html)

    def test_bouton_relie_a_un_formulaire(self):
        """Un bouton hors de son formulaire l'envoie par l'attribut form."""
        html = render(
            '{% button "Enregistrer" icon="save" variant="ghost" icon_only=True'
            ' form="note-form" %}'
        )

        self.assertIn('<button type="submit" form="note-form"', html)

    def test_lien_relie_a_un_formulaire_refuse(self):
        with self.assertRaises(ValueError):
            render('{% button "Enregistrer" href="/x/" form="note-form" %}')

    def test_lien_desactive_refuse(self):
        with self.assertRaises(ValueError):
            render('{% button "Supprimer" href="/x/" disabled=True %}')

    def test_variante_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            render('{% button "OK" variant="autre" %}')


class TagListTests(SimpleTestCase):
    TAG = (
        "rounded-2xl border border-slate-300 bg-slate-200"
        " px-[.4rem] py-[.1rem] text-[.8rem] font-semibold"
    )

    def test_liste_de_tags(self):
        html = render("{% tag_list tags %}", tags=["a", "<b>"])

        self.assertHTMLEqual(
            html,
            '<ul class="m-0 flex h-fit list-none flex-wrap gap-[.4rem] p-0">'
            f'<li class="{self.TAG}">a</li>'
            f'<li class="{self.TAG}">&lt;b&gt;</li>'
            "</ul>",
        )

    def test_liste_vide(self):
        html = render("{% tag_list tags %}", tags=[])

        self.assertHTMLEqual(html, "")


class LoadUiLibraryTests(SimpleTestCase):
    def test_bibliotheque_chargee_sans_requete(self):
        """Les composants hors navigation n'ont pas besoin de la requête."""
        html = Template('{% load ui %}{% button "OK" %}').render(Context())

        self.assertIn(">OK</button>", html)
