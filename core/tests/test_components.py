"""Tests des composants d'interface partagés (balises de `core/templatetags/ui.py`)."""

from django.template import Context, RequestContext, Template
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from core.icons import icon_svg
from core.templatetags.ui import BUTTON_VARIANTS

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
            f' hover:bg-white" href="{reverse("todolist:index")}"'
            ' title="Accueil" aria-label="Accueil">'
            f"{icon_svg('home')}"
            '<span class="font-medium whitespace-nowrap'
            ' group-data-collapsed/nav:hidden">Accueil</span>'
            "</a>",
        )

    def test_lien_actif_sur_la_page_courante(self):
        url = reverse("todolist:index")

        html = render('{% nav_link "todolist:index" "Accueil" "home" %}', path=url)

        self.assertIn("hover:bg-white bg-white", html)
        self.assertIn('aria-current="page"', html)


class ButtonTests(SimpleTestCase):
    def test_classes_des_variantes(self):
        """Règles des variantes (#145) : une forme commune ; les boutons pleins
        s'éclaircissent au survol ; un ghost n'a de fond qu'au survol ; les
        suppressions ont le texte rouge."""
        self.assertEqual(
            BUTTON_VARIANTS,
            {
                "primary": PRIMARY,
                "danger": DANGER,
                "ghost": GHOST,
                "ghost-danger": GHOST_DANGER,
            },
        )

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
            f"{icon_svg('save')}"
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
            f"{icon_svg('edit')}"
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

    def test_bouton_decrit_par_un_element(self):
        """Un bouton désactivé reste relié au texte qui explique pourquoi."""
        html = render(
            '{% button "Supprimer" variant="ghost-danger" disabled=True'
            ' describedby="raison" %}'
        )

        self.assertIn('aria-describedby="raison"', html)

    def test_bouton_qui_ouvre_une_popover(self):
        """Popover native (attribut `popover`) : le navigateur l'ouvre et la ferme."""
        html = render(
            '{% button "Annuler" type="button" popovertarget="p"'
            ' popovertargetaction="hide" %}'
        )

        self.assertIn('popovertarget="p" popovertargetaction="hide"', html)

    def test_lien_qui_ouvre_une_popover_refuse(self):
        with self.assertRaises(ValueError):
            render('{% button "Voir" href="/x/" popovertarget="p" %}')

    def test_lien_relie_a_un_formulaire_refuse(self):
        with self.assertRaises(ValueError):
            render('{% button "Enregistrer" href="/x/" form="note-form" %}')

    def test_lien_desactive_refuse(self):
        with self.assertRaises(ValueError):
            render('{% button "Supprimer" href="/x/" disabled=True %}')

    def test_variante_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            render('{% button "OK" variant="autre" %}')


class KbdTests(SimpleTestCase):
    def test_raccourci_en_kbd(self):
        html = render('{% kbd "←" %}')

        self.assertHTMLEqual(
            html,
            '<kbd class="rounded border border-slate-300 bg-white px-1 text-xs'
            ' text-slate-600">←</kbd>',
        )

    def test_texte_echappe(self):
        self.assertIn("&lt;b&gt;", render("{% kbd keys %}", keys="<b>"))


class ButtonShortcutTests(SimpleTestCase):
    def test_raccourci_annonce_sur_un_lien(self):
        html = render('{% button "Suivant" href="/x/" keyshortcuts="ArrowRight" %}')

        self.assertIn('aria-keyshortcuts="ArrowRight"', html)

    def test_raccourci_annonce_sur_un_bouton(self):
        html = render('{% button "Suivant" keyshortcuts="Control+S" %}')

        self.assertIn('aria-keyshortcuts="Control+S"', html)

    def test_pas_d_attribut_sans_raccourci(self):
        self.assertNotIn("aria-keyshortcuts", render('{% button "Suivant" %}'))


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


class ConfirmButtonTests(SimpleTestCase):
    """`{% confirm_button %}` : popover native, sans JavaScript (#292)."""

    SOURCE = (
        '{% confirm_button "Supprimer le projet" id="delete-p1" icon="delete"'
        ' icon_only=True message="Supprimer « A » ?" action="/projects/1/delete/" %}'
    )

    def test_le_bouton_ouvre_la_popover(self):
        html = render(self.SOURCE)

        self.assertIn('type="button"', html)
        self.assertIn('aria-label="Supprimer le projet"', html)
        self.assertIn('popovertarget="delete-p1"', html)
        self.assertIn(f'class="{GHOST_DANGER}"', html)

    def test_la_popover_porte_le_message_et_le_formulaire(self):
        html = render(self.SOURCE)

        self.assertIn(
            '<div id="delete-p1" popover class="confirm-popover min-w-48 max-w-80', html
        )
        self.assertIn('<p class="mb-3 font-semibold">Supprimer « A » ?</p>', html)
        self.assertIn('<form method="post" action="/projects/1/delete/"', html)
        self.assertIn('name="csrfmiddlewaretoken"', html)
        self.assertNotIn("data-confirm", html)

    def test_annuler_puis_l_action_en_danger_par_defaut(self):
        html = render(self.SOURCE)

        cancel = html.index('popovertarget="delete-p1" popovertargetaction="hide"')
        action = html.index('type="submit"')
        self.assertLess(cancel, action)
        self.assertIn(f'<button type="submit" class="{DANGER}"', html)
        self.assertIn(">Supprimer</button>", html)

    def test_libelle_et_variante_de_l_action(self):
        html = render(
            '{% confirm_button "Rétablir" id="r" icon="restore_from_trash"'
            ' variant="ghost" message="Rétablir ?" action="/x/"'
            ' confirm_label="Rétablir" confirm_icon="restore_from_trash"'
            ' confirm_variant="primary" %}'
        )

        self.assertIn(f'<button type="submit" class="{PRIMARY}"', html)
        self.assertIn(f'class="{GHOST}"', html)

    def test_desactive_sans_popover_et_relie_a_sa_raison(self):
        html = render(
            '{% confirm_button "Supprimer" id="p" icon="delete" icon_only=True'
            ' message="?" action="/x/" disabled=True describedby="raison" %}'
        )

        self.assertIn(" disabled", html)
        self.assertIn('aria-describedby="raison"', html)
        self.assertNotIn("popover", html)
        self.assertNotIn("<form", html)
