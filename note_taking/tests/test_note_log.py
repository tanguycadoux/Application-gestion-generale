"""Chaque modification d'une note est tracée (#468) : source, versions, tailles."""

import ast
import logging
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Project
from note_taking.models import Note
from note_taking.quick_capture import capture
from note_taking.renaming import located, rename_project_titles, rename_titles
from note_taking.services import process_passages

DAY = "2025-11-24"
QMD = "---\ndate: {}\n---\n\n# P\nx"


class NoteLogTests(TestCase):
    def setUp(self):
        self.note = Note.objects.create(date=DAY, body="# P\ntexte")
        process_passages(self.note)

    def lines(self, action) -> list[str]:
        """Lignes `INFO` écrites une fois la transaction validée."""
        with self.assertLogs("note_taking", logging.INFO) as logs:
            with self.captureOnCommitCallbacks(execute=True):
                action()
        return [r.getMessage() for r in logs.records if r.levelno == logging.INFO]

    def assertSource(self, source: str, action, date: str = DAY) -> None:
        (line,) = self.lines(action)
        self.assertIn(f"Note {date}", line)
        self.assertIn(f"source={source} ", line)
        self.assertEqual(Note.objects.get(date=date).updated_by, source)

    def edit(self, **fields):
        url = reverse("note_taking:edit_note", args=[DAY])
        return self.client.post(url, {"date": DAY, "body": "# P\nautre", **fields})

    def test_editeur(self):
        self.assertSource("editor", self.edit)

    def test_remplacement_force(self):
        current = Note.objects.get().updated.isoformat()

        self.assertSource(
            "overwrite",
            lambda: self.edit(version="2020-01-01T00:00:00+00:00", overwrite=current),
        )

    def test_nouvelle_note(self):
        url = reverse("note_taking:new_note")

        self.assertSource(
            "editor",
            lambda: self.client.post(url, {"date": "2025-11-25", "body": "x"}),
            date="2025-11-25",
        )

    def test_capture_rapide(self):
        self.assertSource(
            "capture", lambda: capture("ligne"), date=str(timezone.localdate())
        )

    def test_renommage_de_projet(self):
        self.assertSource(
            "project_rename",
            lambda: rename_project_titles(Project.objects.get(), "P", "Q"),
        )

    def test_import(self):
        file = SimpleUploadedFile("2025-11-26.qmd", QMD.format("2025-11-26").encode())

        self.assertSource(
            "import",
            lambda: self.client.post(
                reverse("note_taking:import_files"), {"import_files": [file]}
            ),
            date="2025-11-26",
        )

    def test_fichier_source(self):
        file = SimpleUploadedFile(f"{DAY}.qmd", QMD.format(DAY).encode())
        url = reverse("note_taking:update_source_file", args=[DAY])

        self.assertSource(
            "source_file",
            lambda: self.client.post(url, {"note_update_source_file": file}),
        )

    def test_renommage_de_chemin(self):
        self.note.body = "# P\n## Avant\ntexte"
        self.note.save()
        process_passages(self.note)
        project = Project.objects.get()
        (key,) = [found.key for found in located(project, ["Avant"])]

        self.assertSource(
            "path_rename", lambda: rename_titles(project, ["Avant"], "Après", [key])
        )

    def test_versions_et_tailles(self):
        before = Note.objects.get()

        (line,) = self.lines(self.edit)

        after = Note.objects.get()
        self.assertIn(
            f"version={before.updated.isoformat()} -> {after.updated.isoformat()}", line
        )
        self.assertIn(f"taille={len(before.body)} -> {len(after.body)}", line)

    def test_texte_jamais_dans_le_log(self):
        (line,) = self.lines(lambda: self.edit(body="# P\nsecret"))

        self.assertNotIn("secret", line)

    def test_source_inconnue_ne_garde_pas_la_precedente(self):
        self.note.save(source=Note.Source.CAPTURE)

        self.note.save()

        self.assertEqual(Note.objects.get().updated_by, "")

    def test_ecriture_annulee_non_tracee(self):
        """Une écriture annulée avec sa transaction n'a rien modifié."""
        with self.assertNoLogs("note_taking", logging.INFO):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(ZeroDivisionError), transaction.atomic():
                    self.note.save(source=Note.Source.CAPTURE)
                    raise ZeroDivisionError


class SingleWritePointTests(SimpleTestCase):
    """`Note.save(source=…)` est le seul point d'écriture du texte."""

    def test_toute_ecriture_dit_sa_source(self):
        missing = []
        found = 0
        for app in ("core", "note_taking", "todolist"):
            for path in (Path(settings.BASE_DIR) / app).rglob("*.py"):
                if {"tests", "migrations"} & set(path.parts):
                    continue
                for call in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "save"
                        and isinstance(call.func.value, ast.Name)
                        and call.func.value.id == "note"
                    ):
                        found += 1
                        if not any(k.arg == "source" for k in call.keywords):
                            missing.append(f"{path.name}:{call.lineno}")
        self.assertGreater(found, 5)
        self.assertEqual(missing, [])


class LoggingSettingsTests(SimpleTestCase):
    def test_fichier_a_rotation(self):
        handler = settings.LOGGING["handlers"]["file"]

        self.assertEqual(handler["class"], "logging.handlers.RotatingFileHandler")
        self.assertEqual(Path(handler["filename"]).name, "app.log")
        self.assertGreater(handler["maxBytes"], 0)
        self.assertGreater(handler["backupCount"], 0)

    def test_loggers(self):
        loggers = settings.LOGGING["loggers"]

        for name in ("core", "images", "note_taking", "todolist"):
            with self.subTest(name=name):
                self.assertEqual(loggers[name]["level"], "INFO")
                self.assertIn("file", loggers[name]["handlers"])
        self.assertEqual(loggers["django.request"]["level"], "WARNING")
        self.assertIn("file", loggers["django.request"]["handlers"])

    def test_les_tests_n_ecrivent_pas_dans_le_fichier(self):
        for name in ("core", "note_taking", "todolist", "django.request"):
            for handler in logging.getLogger(name).handlers:
                self.assertNotIsInstance(handler, logging.FileHandler)
