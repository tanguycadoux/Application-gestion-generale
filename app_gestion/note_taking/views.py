from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from pathlib import Path
import markdown

from .models import Note
from .utils import insert_note_in_table, parse_note_as_dict


def index(request):
    context = {}

    return render(request, "note_taking/index.html", context)

def notes_list(request):
    qmd_files = sorted(
        [f.name for f in settings.NOTES_DIR.glob("*.qmd")],
        reverse=True
    )

    notes = []

    for file in qmd_files:
        notes.append({"date": Path(file).stem})

    context = {
        "notes": notes,
        "notes_objects": Note.objects.all().order_by('-date'),
        "nb_files": len(qmd_files),
        "nb_objects": len(Note.objects.all()),
        }

    return render(request, "note_taking/notes_list.html", context)

def note_md(request, pk):
    # TO DELETE
    # filename = f'{date}.qmd'
    # note_path = settings.NOTES_DIR / filename

    # if not note_path.exists() or not note_path.suffix == ".qmd":
    #     raise Http404("Note not found.")
    
    # with open(note_path, "r", encoding="utf-8") as f:
    #     content = f.read()

    note = get_object_or_404(Note, pk=pk)
    
    html_content = markdown.markdown(note.raw, extensions=["fenced_code", "tables"])    
    
    context = {
        "date": note.date,
        "content": html_content,
    }

    return render(request, "note_taking/note_md.html", context)

def import_note(request):
    if request.method == "POST":
        try:
            file = request.FILES["note_import"]
            insert_note_in_table(file)
            messages.success(request, "La note est ajoutée.")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout de la note : {e}")
    return redirect(request.META.get('HTTP_REFERER', '/'))

# def overwrite_notes(request):
#     if request.method == "POST":
#         source_folder = request.POST.get("source_folder")
#         project_notes_folder = settings.NOTES_DIR
#         try:
#             archive_folder(project_notes_folder)
#             copy_folder_contents(source_folder, project_notes_folder)
#             messages.success(request, "Le dossier est synchronisé.")
#         except Exception as e:
#             messages.error(request, f"Erreur lors de la synchronisation : {e}")
#     return redirect(request.META.get('HTTP_REFERER', '/'))

# def synchronize_notes(request):
#     try:
#         new_notes = []
#         for filepath in Path(settings.NOTES_DIR).glob('*.qmd'):
#             filename = Path(filepath)
#             try:
#                 note = insert_note_in_table(filename)
#                 new_notes.append(note)
#             except Exception as e:
#                 messages.error(request, f"Erreur lors de l'ajout de la note {filename} : {e}")
#         messages.success(request, f'{len(new_notes)} notes ont été ajoutées.')
#     except Exception as e:
#         messages.error(request, f"Erreur lors de la synchronisation : {e}")        
#     return redirect(request.META.get('HTTP_REFERER', '/'))

def note_json(request, pk):
    note = get_object_or_404(Note, pk=pk)
    return JsonResponse(parse_note_as_dict(note))
