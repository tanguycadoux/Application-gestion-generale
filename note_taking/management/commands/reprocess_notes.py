from django.core.management.base import BaseCommand
from django.db import transaction

from note_taking.exceptions import NoteError
from note_taking.models import Note
from note_taking.services import process_note_parts


class Command(BaseCommand):
    help = (
        "Recalcule les note parts de toutes les notes. Les tâches existantes "
        "ne sont ni recréées ni modifiées."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulation : affiche le résultat sans rien enregistrer.",
        )

    def handle(self, *args, dry_run: bool = False, **options):
        processed = 0
        errors = 0

        with transaction.atomic():
            for note in Note.objects.order_by("date"):
                try:
                    # Une note en erreur est annulée sans bloquer les autres.
                    with transaction.atomic():
                        process_note_parts(note)
                except NoteError as e:
                    errors += 1
                    self.stderr.write(f"Échec pour la note du {note.date} : {e}")
                else:
                    processed += 1

            if dry_run:
                transaction.set_rollback(True)

        summary = f"{processed} note(s) recalculée(s), {errors} erreur(s)."
        if dry_run:
            summary += " Simulation : rien n'a été enregistré."
        self.stdout.write(self.style.SUCCESS(summary) if not errors else summary)
