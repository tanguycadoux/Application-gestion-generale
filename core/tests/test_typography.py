"""Espaces insécables de la typographie française (#383).

Une espace insécable (U+00A0) avant `;`, `:`, `!`, `?` et `»`, et après `«` :
le navigateur ne coupe plus la ligne entre le mot et sa ponctuation.
"""

from pathlib import Path

from django.conf import settings
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.safestring import SafeString, mark_safe

from core.models import Project
from core.typography import nbsp_punct

NBSP = " "


def render(source: str, **context) -> str:
    return Template("{% load ui %}" + source).render(Context(context))


class NbspPunctTests(SimpleTestCase):
    def test_avant_les_ponctuations_doubles(self):
        self.assertEqual(
            nbsp_punct("Rien n'a été modifié ; recommencer : oui ! non ?"),
            f"Rien n&#x27;a été modifié{NBSP}; recommencer{NBSP}: oui{NBSP}! non{NBSP}?",
        )

    def test_dans_les_guillemets(self):
        self.assertEqual(
            nbsp_punct("Le projet « ASTERICS » est supprimé."),
            f"Le projet «{NBSP}ASTERICS{NBSP}» est supprimé.",
        )

    def test_espace_deja_insecable_gardee(self):
        for space in (NBSP, " "):
            with self.subTest(space=space):
                self.assertEqual(
                    nbsp_punct(f"Bilan{space}: «{space}x{space}»"),
                    f"Bilan{space}: «{space}x{space}»",
                )

    def test_pas_de_double_espace(self):
        self.assertEqual(
            nbsp_punct(f"Bilan  :{NBSP}«  x {NBSP}»"),
            f"Bilan{NBSP}:{NBSP}«{NBSP}x{NBSP}»",
        )

    def test_sans_espace_rien_n_est_ajoute(self):
        """Une heure, une adresse ou un `chemin:` ne prennent pas d'espace."""
        self.assertEqual(
            nbsp_punct("10:30 https://x chemin:a"), "10:30 https://x chemin:a"
        )

    def test_texte_echappe(self):
        result = nbsp_punct("<b>gras</b> : & ?")

        self.assertIsInstance(result, SafeString)
        self.assertEqual(result, f"&lt;b&gt;gras&lt;/b&gt;{NBSP}: &amp;{NBSP}?")

    def test_html_sur_modifie_hors_des_balises(self):
        """Dans du HTML déjà sûr, seul le texte change : ni les attributs, ni le
        code (`<code>`, `<kbd>`, `<pre>`)."""
        html = mark_safe(
            '<a title="a : b" href="?q=x :y">Lien : ici</a>'
            " <code>chemin :a</code> <kbd>Ctrl :</kbd> <pre>a ;</pre> fin !"
        )

        self.assertEqual(
            nbsp_punct(html),
            f'<a title="a : b" href="?q=x :y">Lien{NBSP}: ici</a>'
            f" <code>chemin :a</code> <kbd>Ctrl :</kbd> <pre>a ;</pre> fin{NBSP}!",
        )

    def test_filtre_du_gabarit(self):
        self.assertEqual(
            render("{{ t|nbsp_punct }}", t="<i>a</i> ?"),
            f"&lt;i&gt;a&lt;/i&gt;{NBSP}?",
        )

    def test_bloc_filter_du_gabarit(self):
        """`{% filter nbsp_punct %}` pour un texte écrit dans le gabarit : les
        variables y restent échappées."""
        self.assertEqual(
            render(
                "{% filter nbsp_punct %}Renommer « {{ n }} »{% endfilter %}", n="<x>"
            ),
            f"Renommer «{NBSP}&lt;x&gt;{NBSP}»",
        )

    def test_composants(self):
        confirm = render(
            '{% confirm_button "Supprimer" id="c" message="Supprimer ce projet ?" action="/x/" %}'
        )
        self.assertIn(f"Supprimer ce projet{NBSP}?", confirm)

        button = render('{% button "Suivant : étape 2" %}')
        self.assertIn(f"Suivant{NBSP}: étape 2", button)

    def test_toast_cree_par_script(self):
        """`Toast.show` applique la même règle au texte qu'il place."""
        script = (Path(settings.BASE_DIR) / "core/static/core/toasts.js").read_text()

        self.assertIn("nbspPunct(message)", script)


class MessageToastTypographyTests(TestCase):
    def test_message_reel_en_toast(self):
        project = Project.objects.create(name="ASTERICS <b>")

        response = self.client.post(
            reverse("core:project_delete", args=[project.pk]), follow=True
        )

        self.assertContains(
            response, f"Le projet «{NBSP}ASTERICS &lt;b&gt;{NBSP}» est supprimé."
        )
