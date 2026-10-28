"""Service de recherche (#199) : la requête analysée appliquée aux note parts."""

from django.test import TestCase

from core.models import Project, Section, Tag
from note_taking.models import Note, NotePart
from note_taking.search import search_note_parts
from note_taking.search_query import parse_query


class SearchServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alpha = Project.objects.create(name="Alpha")
        cls.beta = Project.objects.create(name="Béta Deux")
        cls.reunion = Section.objects.create(project=cls.alpha, name="Réunion")
        cls.prepa = Section.objects.create(
            project=cls.alpha, parent=cls.reunion, name="Préparation"
        )
        cls.beta_reunion = Section.objects.create(project=cls.beta, name="Réunion")
        cls.urgent = Tag.objects.create(name="urgent")
        cls.fini = Tag.objects.create(name="fini")
        cls.sept = Note.objects.create(date="2026-09-10")
        cls.oct = Note.objects.create(date="2026-10-15")

        cls.p1 = cls.part(cls.sept, cls.alpha, "banc thermique brouillon", cls.reunion)
        cls.p2 = cls.part(cls.oct, cls.alpha, "banc de résistance thermique", cls.prepa)
        cls.p3 = cls.part(cls.oct, cls.beta, "résistance seule", cls.beta_reunion)
        cls.p4 = cls.part(cls.oct, cls.beta, "rien à voir", None)
        cls.p1.tags.set([cls.urgent])
        cls.p2.tags.set([cls.urgent, cls.fini])
        cls.p3.tags.set([cls.fini])

    @staticmethod
    def part(note, project, content, section):
        return NotePart.objects.create(
            note=note, project=project, section=section, content=content
        )

    def search(self, text, projects=(), sections=()):
        return search_note_parts(parse_query(text), projects, sections)

    def test_rien_a_chercher(self):
        self.assertIsNone(self.search(""))
        self.assertIsNone(self.search("  "))
        self.assertIsNone(self.search(", ;"))

    def test_texte_libre(self):
        self.assertEqual(set(self.search("thermique")), {self.p1, self.p2})

    def test_tous_les_mots(self):
        self.assertEqual(self.search("banc résistance"), [self.p2])

    def test_sans_accents_ni_casse(self):
        self.assertEqual(self.search("RESISTANCE seule"), [self.p3])

    def test_phrase_exacte(self):
        self.assertEqual(self.search('"résistance thermique"'), [self.p2])
        self.assertEqual(self.search('"thermique résistance"'), [])

    def test_prefixe(self):
        self.assertEqual(set(self.search("therm*")), {self.p1, self.p2})
        # Sans astérisque, pas de préfixe (et sans élargissement aux fautes, #200).
        self.assertEqual(search_note_parts(parse_query("thermiq"), expand=False), [])

    def test_exclusion(self):
        self.assertEqual(self.search("thermique -brouillon"), [self.p2])

    def test_exclusion_seule(self):
        self.assertEqual(set(self.search("-thermique")), {self.p3, self.p4})

    def test_exclusion_d_une_phrase(self):
        self.assertEqual(set(self.search('banc -"résistance thermique"')), {self.p1})

    def test_projet(self):
        self.assertEqual(set(self.search("projet:alpha")), {self.p1, self.p2})

    def test_projet_a_espaces_sans_accents(self):
        self.assertEqual(set(self.search('projet:"beta deux"')), {self.p3, self.p4})

    def test_projets_repetes_se_cumulent(self):
        self.assertEqual(
            set(self.search('projet:Alpha projet:"Béta Deux"')),
            {self.p1, self.p2, self.p3, self.p4},
        )

    def test_projet_inconnu_ne_trouve_rien(self):
        self.assertEqual(self.search("projet:Zeta"), [])

    def test_exclure_un_projet(self):
        self.assertEqual(set(self.search("-projet:alpha")), {self.p3, self.p4})

    def test_tag(self):
        self.assertEqual(set(self.search("tag:urgent")), {self.p1, self.p2})

    def test_tags_repetes_sont_tous_requis(self):
        self.assertEqual(self.search("tag:urgent tag:fini"), [self.p2])

    def test_exclure_un_tag(self):
        self.assertEqual(set(self.search("tag:urgent -tag:fini")), {self.p1})

    def test_chemin_avec_descendants(self):
        self.assertEqual(
            set(self.search("chemin:Réunion")), {self.p1, self.p2, self.p3}
        )

    def test_chemin_a_plusieurs_niveaux(self):
        self.assertEqual(self.search("chemin:Réunion/Préparation"), [self.p2])
        self.assertEqual(self.search('chemin:"réunion / preparation"'), [self.p2])

    def test_chemin_et_projet(self):
        self.assertEqual(
            set(self.search('chemin:Réunion projet:"Béta Deux"')), {self.p3}
        )

    def test_chemin_inconnu(self):
        self.assertEqual(self.search("chemin:Préparation"), [])

    def test_exclure_un_chemin(self):
        self.assertEqual(set(self.search("-chemin:Réunion")), {self.p4})

    def test_date_d_un_mois(self):
        self.assertEqual(set(self.search("date:2026-10")), {self.p2, self.p3, self.p4})

    def test_date_d_un_jour(self):
        self.assertEqual(set(self.search("date:2026-09-10")), {self.p1})

    def test_plage_de_dates(self):
        self.assertEqual(
            set(self.search("date:2026-09..2026-10")),
            {self.p1, self.p2, self.p3, self.p4},
        )
        self.assertEqual(
            set(self.search("date:2026-10-01..")), {self.p2, self.p3, self.p4}
        )
        self.assertEqual(set(self.search("date:..2026-09")), {self.p1})

    def test_tout_ensemble(self):
        self.assertEqual(
            self.search("banc tag:fini date:2026-10 projet:alpha -brouillon"),
            [self.p2],
        )

    def test_filtres_de_la_page_s_ajoutent_a_la_requete(self):
        self.assertEqual(
            self.search(
                "thermique", projects=[self.alpha.pk], sections=[self.prepa.pk]
            ),
            [self.p2],
        )

    def test_filtres_de_la_page_sans_texte(self):
        self.assertEqual(
            set(self.search("", projects=[self.beta.pk])), {self.p3, self.p4}
        )

    def test_sans_texte_la_plus_recente_d_abord(self):
        results = self.search("projet:alpha")

        self.assertEqual(results, [self.p2, self.p1])

    def test_avec_texte_la_plus_pertinente_d_abord(self):
        courte = self.part(self.sept, self.alpha, "thermique", None)

        results = self.search("thermique")

        self.assertEqual(results[0], courte)

    def test_texte_mal_forme_ne_plante_pas(self):
        for text in ['"', "date:abc", "projet:", 'tag:"x', "a OR", "NEAR(a b)", "(*"]:
            with self.subTest(text=text):
                self.search(text)
