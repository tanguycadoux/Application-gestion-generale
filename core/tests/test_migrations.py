"""Tests des migrations de données de core."""

import unittest
from importlib import import_module

from django.apps import apps
from django.test import TestCase

from core.models import Project


class ClearDescriptionsTests(TestCase):
    """#243 : une description identique au nom du projet est vidée."""

    @unittest.expectedFailure
    def test_description_egale_au_nom_videe_les_autres_gardees(self):
        migration = import_module("core.migrations.0005_clear_project_descriptions")
        same = Project.objects.create(name="ASTERICS", description="ASTERICS")
        other = Project.objects.create(name="ICONE", description="Projet ICONE")
        case = Project.objects.create(name="Misc", description="misc")

        migration.clear_descriptions(apps, None)

        for project, expected in ((same, ""), (other, "Projet ICONE"), (case, "misc")):
            with self.subTest(project=project.name):
                project.refresh_from_db()
                self.assertEqual(project.description, expected)
