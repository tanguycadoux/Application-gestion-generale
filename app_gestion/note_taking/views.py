from django.conf import settings
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect
from pathlib import Path
import markdown

from .models import Note
from .utils import copy_folder_contents, archive_folder, validate_date_format, insert_note_in_table


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

def note_md(request, date):
    filename = f'{date}.qmd'
    note_path = settings.NOTES_DIR / filename

    if not note_path.exists() or not note_path.suffix == ".qmd":
        raise Http404("Note not found.")
    
    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    html_content = markdown.markdown(content, extensions=["fenced_code", "tables"])    
    
    context = {
        "date": date,
        "filename": filename,
        "content": html_content,
    }

    return render(request, "note_taking/note_md.html", context)

def import_note(request):
    if request.method == "POST":
        try:
            file = request.FILES["note_import"]
            storage = FileSystemStorage(location=settings.NOTES_DIR)
            storage.save(file.name, file)
            messages.success(request, "La note est ajoutée.")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout de la note : {e}")
    return redirect(request.META.get('HTTP_REFERER', '/'))

def overwrite_notes(request):
    if request.method == "POST":
        source_folder = request.POST.get("source_folder")
        project_notes_folder = settings.NOTES_DIR
        try:
            archive_folder(project_notes_folder)
            copy_folder_contents(source_folder, project_notes_folder)
            messages.success(request, "Le dossier est synchronisé.")
        except Exception as e:
            messages.error(request, f"Erreur lors de la synchronisation : {e}")
    return redirect(request.META.get('HTTP_REFERER', '/'))

def synchronize_notes(request):
    try:
        new_notes = []
        for filepath in Path(settings.NOTES_DIR).glob('*.qmd'):
            filename = Path(filepath)
            try:
                note = insert_note_in_table(filename)
                new_notes.append(note)
            except Exception as e:
                messages.error(request, f"Erreur lors de l'ajout de la note {filename} : {e}")
        messages.success(request, f'{len(new_notes)} notes ont été ajoutées.')
    except Exception as e:
        messages.error(request, f"Erreur lors de la synchronisation : {e}")        
    return redirect(request.META.get('HTTP_REFERER', '/'))

def note_json(request, date):
    filename = f'{date}.qmd'
    note_path = settings.NOTES_DIR / filename

    if not note_path.exists() or not note_path.suffix == ".qmd":
        raise Http404("Note not found.")
    
    json_content = {
        'File date': date,
        'Note metadata': [],
        'Content': [],
        }
    
    with open(note_path, "r", encoding="utf-8") as f:
        is_note_metadata = False
        is_local_metadata = False
        is_code_block = False
        is_title_line = False
        project = ""
        subject = ""
        titles_three_to_six = [""]*4
        local_metadata_tags = set()
        for i, line in enumerate(f):
            line = line.rstrip('\n')

            if line == '---':
                is_note_metadata = not(is_note_metadata)
                continue
            if line == r'::: {.metadata}':
                is_local_metadata = True
                continue
            if line == ':::':
                is_local_metadata = False
                continue
            
            if line[0:3] == '```':
                is_code_block = not(is_code_block)
            
            if not(is_code_block):
                for j in range(1, 7):
                    if line[0:j+1] == f'{"#"*j} ':
                        is_title_line = True
                        title_text = line[j+1:]
                        match j:
                            case 1:
                                project = title_text
                                subject = ""
                                titles_three_to_six = [""]*4
                            case 2:
                                subject = title_text
                                titles_three_to_six = [""]*4
                            case 3:
                                titles_three_to_six[0] = title_text
                                titles_three_to_six[1] = ""
                                titles_three_to_six[2] = ""
                                titles_three_to_six[3] = ""
                            case 4:
                                titles_three_to_six[1] = title_text
                                titles_three_to_six[2] = ""
                                titles_three_to_six[3] = ""
                            case 5:
                                titles_three_to_six[2] = title_text
                                titles_three_to_six[3] = ""
                            case 6:
                                titles_three_to_six[3] = title_text
                        break
                    else:
                        is_title_line = False
            if is_title_line:
                local_metadata_tags = set()
                continue

            if is_note_metadata and is_local_metadata:
                raise ValueError(f'Erreur dans la lecture du fichier {filename} :  (ligne numéro {i+1} : {line})')
            
            if is_note_metadata:
                line_parsed = line.split(':')
                if len(line_parsed) != 2:
                    raise ValueError(f'La métadonnée locale du fichier {filename} est erronnée : format non type DICT (ligne numéro {i+1} : {line})')
                parsed_variable = line_parsed[0].strip()
                parsed_value    = line_parsed[1].strip()
                json_content['Note metadata'].append({parsed_variable: parsed_value})
            elif is_local_metadata:
                line_parsed = line.split(':')
                if len(line_parsed) != 2:
                    raise ValueError(f'La métadonnée locale du fichier {filename} est erronnée : format non type DICT (ligne numéro {i+1} : {line})')
                parsed_variable = line_parsed[0].strip()
                parsed_value    = line_parsed[1].strip()
                if parsed_variable == 'tags':
                    if parsed_value[0] != "[" or parsed_value[-1] != "]":
                        raise ValueError(f'La métadonnée locale du fichier {filename} est erronnée : format non type ARRAY (ligne numéro {i+1} : {line})')
                    parsed_tags = parsed_value.strip('[]').split(',')
                    for tag in parsed_tags:
                        local_metadata_tags.add(tag.strip())
            else:
                tags = local_metadata_tags | {t for t in titles_three_to_six if t}
                print(tags)
                append_new = True
                for json_line in json_content['Content']:
                    json_line_tags = set(json_line["Tags"])
                    if project == json_line["Project"] and subject == json_line["Subject"] and tags == json_line_tags:
                        append_new = False
                        json_line["Content"].append(line)
                        break
                if append_new:
                    json_content['Content'].append({
                        "Project": project,
                        "Subject": subject,
                        "Tags": list(tags),
                        "Content": [line],
                    })
    
    lines_to_remove = []
    for i, json_line in enumerate(json_content['Content']):
        if json_line["Content"] == [""]:
            lines_to_remove.append(i)
    for i in reversed(lines_to_remove):
        json_content['Content'].pop(i)
    
    for json_line in json_content['Content']:
        while json_line['Content'][0] == "":
            json_line['Content'].pop(0)
        while json_line['Content'][-1] == "":
            json_line['Content'].pop(-1)
    
    return JsonResponse(json_content)
