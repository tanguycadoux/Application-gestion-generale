from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from note_taking.exceptions import NoteError
from note_taking.models import Note
from note_taking.qmd.parser import HEADING_SEPARATOR
from note_taking.qmd.todo_sections import Conversion, convert_todo_sections
from note_taking.services import process_note_parts
from todolist.models import Todo
from todolist.services import lines_of


@dataclass(frozen=True)
class Move:
    """Une tâche déjà créée que la conversion range sous un autre chemin : la
    liste qui suivait `### TODO` passe sous le titre qui le précédait."""

    note: Note
    path: str
    new_path: str
    text: str


def moves_of(note: Note, found: Conversion) -> list[Move]:
    """Les lignes dont le chemin change, avec leur ancien chemin (celui des tâches
    déjà créées) et le nouveau (celui que l'analyse leur donnera)."""
    moves = []
    for chunk in found.chunks:
        old = lines_of(
            HEADING_SEPARATOR.join(chunk.old_headings), "\n".join(chunk.before), True
        )
        new = lines_of(
            HEADING_SEPARATOR.join(chunk.new_headings), "\n".join(chunk.after), False
        )
        if len(old) != len(new):
            raise CommandError(
                f"Note du {note.date} : la conversion ne donne pas les mêmes lignes "
                "de tâches qu'avant. Rien n'a été modifié."
            )
        for before, after in zip(old, new, strict=True):
            if (before.path, before.text) != (after.path, after.text):
                moves.append(Move(note, before.path, after.path, before.text))
    return moves


def existing_todos(move: Move):
    return Todo.all_objects.filter(
        created_from_note=True,
        note_part_date=move.note.date,
        note_path=move.path,
        note_part_text=move.text,
    )


class Command(BaseCommand):
    help = (
        "Convertit les sections TODO des notes en cases à cocher (#297) : le titre "
        "`TODO` est retiré et chaque élément de la section devient `- [ ] texte`. "
        "Sans --apply, montre seulement ce qui changerait."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Réécrit les notes, après avoir tout vérifié ; sinon, simple aperçu.",
        )

    def handle(self, *args, apply: bool = False, **options):
        # Les notes citent des caractères (« → ») qu'une console Windows en cp1252
        # n'écrit pas : l'aperçu les remplace plutôt que de s'arrêter.
        for stream in (self.stdout._out, self.stderr._out):  # type: ignore[attr-defined]
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure:
                reconfigure(errors="replace")

        conversions = [
            (note, convert_todo_sections(note.body))
            for note in Note.objects.order_by("date")
        ]
        concerned = [(note, found) for note, found in conversions if found.sections]
        moves = [move for note, found in concerned for move in moves_of(note, found)]
        self.show(concerned)
        self.show_moves(moves)
        self.show_boxes(conversions)

        problems = sum(len(found.problems) for _, found in concerned)
        if problems:
            message = (
                f"{problems} point(s) à corriger à la main dans les notes ci-dessus. "
                "Rien n'a été modifié."
            )
            if apply:
                raise CommandError(message)
            self.stdout.write(self.style.WARNING(message))
            return
        if not apply:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{len(concerned)} note(s) à réécrire. Rien n'a été modifié : "
                    "relancer avec --apply pour l'écrire."
                )
            )
            return
        # Les notes qui ont une case vide, sans section TODO, sont recalculées
        # aussi : c'est là que leurs cases deviennent des tâches.
        boxed = [
            note
            for note, found in conversions
            if found.open_boxes and not found.sections
        ]
        self.apply(concerned, moves, boxed)

    def show(self, concerned: list[tuple[Note, Conversion]]) -> None:
        for note, found in concerned:
            self.stdout.write(
                f"\nNote du {note.date} : {found.sections} section(s) TODO, "
                f"{len(found.changes)} ligne(s) modifiée(s)"
            )
            for problem in found.problems:
                self.stdout.write(self.style.ERROR(f"  ! {problem}"))
            for change in sorted(found.changes, key=lambda item: item.number):
                before = change.before.rstrip()
                if change.after is None:
                    self.stdout.write(f"  ligne {change.number} : retirée ({before!r})")
                else:
                    self.stdout.write(
                        f"  ligne {change.number} : {before}  ->  {change.after.rstrip()}"
                    )

    def show_moves(self, moves: list[Move]) -> None:
        """Les tâches déjà créées dont le chemin change : elles gardent leur fiche
        (avancement, échéance, parent) et se rangent sous la section où leur liste
        se trouve une fois le titre `TODO` retiré."""
        existing = [move for move in moves if existing_todos(move).exists()]
        self.stdout.write(
            f"\n{len(existing)} tâche(s) déjà créée(s) changent de chemin (le titre "
            "TODO retiré, leur liste passe sous le titre qui le précédait) :"
        )
        for move in existing:
            self.stdout.write(
                f"  {move.note.date} : « {move.text[:60]} »  {move.path}  ->  "
                f"{move.new_path}"
            )

    def show_boxes(self, conversions: list[tuple[Note, Conversion]]) -> None:
        """Les cases déjà présentes hors des sections TODO : les vides deviennent
        des tâches, les cochées sont ignorées."""
        opened = [
            (note, box) for note, found in conversions for box in found.open_boxes
        ]
        done = [(note, box) for note, found in conversions for box in found.done_boxes]
        self.stdout.write(
            f"\n{len(opened)} case(s) vide(s) hors section TODO, qui deviendront "
            f"des tâches (à revoir dans le bilan de leur note) :"
        )
        for note, box in opened:
            self.stdout.write(f"  {note.date}, ligne {box.number} : {box.text}")
        self.stdout.write(f"\n{len(done)} case(s) cochée(s), ignorée(s) :")
        for note, box in done:
            self.stdout.write(f"  {note.date}, ligne {box.number} : {box.text}")
        self.stdout.write("")

    def apply(
        self,
        concerned: list[tuple[Note, Conversion]],
        moves: list[Move],
        boxed: list[Note],
    ) -> None:
        """Réécrit les notes d'un coup, en rangeant sous leur nouveau chemin les
        tâches déjà créées. Une tâche déjà revue qui perdrait quand même sa ligne
        annule tout (l'identité des tâches, #240, ne doit pas se perdre)."""
        with transaction.atomic():
            before = set(Todo.all_objects.values_list("pk", flat=True))
            known = dict(
                Todo.all_objects.filter(created_from_note=True).values_list(
                    "pk", "note_state"
                )
            )
            for move in moves:
                existing_todos(move).update(note_path=move.new_path)
            for note, found in concerned:
                note.body = found.body
                note.save()
            try:
                for note in [note for note, _ in concerned] + boxed:
                    process_note_parts(note)
            except NoteError as error:
                raise CommandError(f"{error}. Rien n'a été modifié.") from error

            lost = [
                todo
                for todo in Todo.all_objects.filter(
                    pk__in=[
                        pk
                        for pk, state in known.items()
                        if state == Todo.NoteState.REVIEWED
                    ],
                    note_state=Todo.NoteState.TO_REVIEW,
                )
            ]
            if lost:
                titles = ", ".join(f"« {todo.title} »" for todo in lost[:5])
                raise CommandError(
                    f"{len(lost)} tâche(s) déjà revue(s) perdraient leur ligne "
                    f"({titles}). Rien n'a été modifié."
                )
            created = Todo.all_objects.exclude(pk__in=before).count()

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(concerned)} note(s) réécrite(s), {len(boxed)} autre(s) "
                f"recalculée(s) ; {created} tâche(s) créée(s) depuis des cases déjà "
                "présentes, à revoir dans le bilan de leur note."
            )
        )
