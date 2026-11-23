"""Un titre de projet changé dans l'éditeur d'une note (#170).

Changer `# Alpha` en `# Gamma` dans une note crée, à l'enregistrement, un projet
« Gamma » pour cette note. L'utilisateur voulait peut-être renommer le projet : un
bilan lui fait choisir (`apply_choice`) :

- **tout renommer** (`everywhere`) : « Gamma » rejoint « Alpha », qui prend le nom
  « Gamma » (sa couleur, ses niveaux, ses tâches restent) ; les titres `# Alpha`
  des autres notes sont réécrits ;
- **seulement dans cette note** (`here`) : ce qui est enregistré ; « Gamma » est un
  autre projet ;
- **ne pas renommer** (`undo`) : le titre de cette note reprend « Alpha », et
  « Gamma », s'il ne sert plus, disparaît.

Le renommage est repéré à l'enregistrement (`record_project_renames`), en comparant
les titres `#` d'avant et d'après, un à un ; il est gardé en base jusqu'au choix
(`PendingProjectRename`), parce que Ctrl+S reste dans l'éditeur (#389). Écrire le
nom d'un projet qui existe déjà n'est pas un renommage : c'est y ranger le texte.
Dans tous les cas, les tâches de la note suivent leur titre, sans doublon
(`note_headings_renamed`, comme le renommage d'un niveau, #299).
"""

from django.db import transaction

from core.projects import forget_project_if_unused, merge_projects, project_named

from .exceptions import NoteRenameError
from .models import Note, PendingProjectRename
from .pending_renames import same_name
from .renaming import headings, project_headings, rename_project_titles, rewrite_titles
from .services import process_passages
from .signals import note_headings_renamed

CHOICES = ("everywhere", "here", "undo")


def project_titles(body: str) -> list[str]:
    """Les titres `#` d'un texte de note, dans l'ordre, tels qu'écrits."""
    return [heading.title for heading in headings(body) if heading.level == 1]


def renamed_projects(old_body: str, new_body: str) -> list[tuple[str, str]]:
    """Les titres de projet renommés entre deux textes d'une note : (ancien, nouveau).

    Les titres `#` se comparent un à un, dans l'ordre ; il faut qu'il y en ait
    autant. Un titre qui n'a changé que de casse est le même projet (#374) ; un
    nom qui reste écrit ailleurs dans la note, ou qui l'était déjà, n'est pas un
    renommage (titres échangés, texte déplacé), ni un ancien nom changé en deux
    nouveaux.
    """
    old, new = project_titles(old_body), project_titles(new_body)
    if len(old) != len(new):
        return []
    pairs: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()
    for before, after in zip(old, new, strict=True):
        if same_name(before, after):
            continue
        if any(same_name(before, title) for title in new) or any(
            same_name(after, title) for title in old
        ):
            continue
        key = before.casefold()
        if key in pairs and not same_name(pairs[key][1], after):
            ambiguous.add(key)
        pairs.setdefault(key, (before, after))
    return [pair for key, pair in pairs.items() if key not in ambiguous]


def follow_tasks(note: Note, old_body: str, new_body: str) -> None:
    """Les tâches de la note suivent ses titres réécrits. Si la note a changé
    ailleurs aussi (passages ajoutés ou retirés), le bilan des tâches s'en charge."""
    try:
        note_headings_renamed.send(
            sender=Note, note=note, old_body=old_body, new_body=new_body
        )
    except NoteRenameError:
        pass


def record_project_renames(note: Note, old_body: str, new_body: str) -> None:
    """À l'enregistrement d'une note, avant le recalcul de ses passages : garde les
    titres de projet renommés, en attente du choix, et fait suivre les tâches."""
    renamed = renamed_projects(old_body, new_body)
    if not renamed:
        return
    for old, new in renamed:
        chained = next(
            (
                pending
                for pending in note.pending_project_renames.all()
                if same_name(pending.new_name, old)
            ),
            None,
        )
        if chained is not None:
            # « Alpha » → « Gamma », puis « Gamma » → « Delta » : « Alpha » → « Delta ».
            if same_name(chained.old_name, new) or project_named(new) is not None:
                chained.delete()
            else:
                chained.new_name = new
                chained.save(update_fields=["new_name"])
            continue
        if project_named(new) is None and project_named(old) is not None:
            PendingProjectRename.objects.create(note=note, old_name=old, new_name=new)
    follow_tasks(note, old_body, new_body)


@transaction.atomic
def apply_choice(pending: PendingProjectRename, choice: str) -> str:
    """Applique le choix fait dans le bilan ; renvoie la phrase du compte rendu."""
    note, old, new = pending.note, pending.old_name, pending.new_name
    pending.delete()
    if choice == "undo":
        numbers = [heading.number for heading in project_headings(note.body, new)]
        old_body = note.body
        note.body = rewrite_titles(old_body, numbers, old)
        note.save()
        follow_tasks(note, old_body, note.body)
        process_passages(note)
        forget_project_if_unused(project_named(new))
        return f"Le titre « {new} » reprend son nom « {old} »."
    if choice == "everywhere":
        keep = project_named(old)
        if keep is not None:
            gone = project_named(new)
            if gone is not None and gone.pk != keep.pk:
                merge_projects(gone, keep)
            keep.name = new
            keep.save(update_fields=["name"])
            report = rename_project_titles(keep, old, new)
            process_passages(note)
            return " ".join([f"Le projet « {old} » est renommé « {new} ».", *report])
    return f"« {new} » est un projet à part ; « {old} » garde son nom."
