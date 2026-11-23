"""Vues de `note_taking`, par domaine (#190).

- `notes` : pages des notes (accueil, tableau, note, création, édition, suppression) ;
- `search` : page de recherche ;
- `saved_searches` : recherches enregistrées (#203) ;
- `transfer` : import et export ;
- `images` : pages et actions des images ;
- `debug` : pages de développement (#235) ;
- `project_renames` : bilan d'un titre de projet renommé dans une note (#170) ;
- `common` : aides partagées (nom d'une note, avertissements, page suivante).

Tout est réexporté ici : `urls.py` écrit `views.NoteDetail`.
"""

from .debug import debug_note_json, note_json
from .images import (
    ImageDetail,
    ImageList,
    delete_image,
    image_capture,
    image_suggestions,
)
from .notes import (
    NoteDetail,
    NoteList,
    delete_note,
    edit_note,
    index,
    new_note,
    note_by_id,
    note_suggestions,
    note_today,
)
from .project_renames import project_rename_review
from .saved_searches import (
    create_saved_search,
    delete_saved_search,
    rename_saved_search,
)
from .search import notes_search
from .transfer import export_note, export_notes, import_files, update_source_file

__all__ = [
    "ImageDetail",
    "ImageList",
    "NoteDetail",
    "NoteList",
    "create_saved_search",
    "debug_note_json",
    "delete_image",
    "delete_note",
    "delete_saved_search",
    "edit_note",
    "export_note",
    "export_notes",
    "image_capture",
    "image_suggestions",
    "import_files",
    "index",
    "new_note",
    "note_by_id",
    "note_json",
    "note_suggestions",
    "note_today",
    "notes_search",
    "project_rename_review",
    "rename_saved_search",
    "update_source_file",
]
