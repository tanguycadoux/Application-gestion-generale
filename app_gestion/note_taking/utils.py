from .models import Note

from datetime import datetime, date
from pathlib import Path
import shutil
import re


def validate_date_format(date_text):
    try:
        date.fromisoformat(date_text)
    except ValueError:
        raise ValueError("Incorrect data format, should be YYYY-MM-DD")

def insert_note_in_table(file):
    filename = Path(file.name).stem

    is_test = filename[:4] == 'TEST'

    if is_test:
        note_date = filename[5:]
    else:
        note_date = filename

    validate_date_format(note_date)
    raw_bytes = file.read()
    raw_content = raw_bytes.decode('utf-8')

    note = Note(date=note_date, is_test=is_test, raw=raw_content)
    note.save()
    return note

def parse_note_as_dict(note: Note) -> dict:
    def parse_text_as_dict(text):
        parsed_text = text.split(':')
        if len(parsed_text) != 2:
            raise ValueError(f'La métadonnée locale est erronnée : format non type DICT ({text})')
        
        parsed_key   = parsed_text[0].strip()
        parsed_value = parsed_text[1].strip()

        return parsed_key, parsed_value
    
    json_content = {
        'File date': note.date,
        'Note metadata': [],
        'Content': [],
        }
    
    is_note_metadata_block = False
    is_local_metadata_block = False
    is_code_block = False
    is_title_line = False
    current_title_level = None
    hierarchy: dict[str, None | str | set] = {
        'project': None,
        'tags_under_project': None,
        'subject': None,
        'tags_under_subject': None,
    }
    for i in range(3, 7):
        hierarchy[f'title_{i}'] = None
        hierarchy[f'tags_under_title_{i}'] = None
    local_metadata_tags = set()
    for i, line in enumerate(note.raw.split('\n')):
        line = line.strip()

        if line.strip() == '---':
            is_note_metadata_block = not(is_note_metadata_block)
            continue

        if line == r'::: {.metadata}':
            is_local_metadata_block = True
            continue

        if is_local_metadata_block and line == ':::':
            is_local_metadata_block = False
            continue

        if line[0:3] == '```':
            is_code_block = not(is_code_block)
        
        # Récupération des titres
        m = re.match(r'^(#+)\s+(.*)', line)
        if m:
            is_title_line = True
            level = len(m.group(1))
            title = m.group(2).strip()
            current_title_level = level

            if level == 1:
                hierarchy['project'] = title
                hierarchy['tags_under_project'] = None
                hierarchy['subject'] = None
                hierarchy['tags_under_subject'] = None
                for j in range(3, 7):
                    hierarchy[f'title_{j}'] = None
                    hierarchy[f'tags_under_title_{j}'] = None
            elif level == 2:
                hierarchy['subject'] = title
                for j in range(3, 7):
                    hierarchy[f'title_{j}'] = None
                    hierarchy[f'tags_under_title_{j}'] = None
            elif level >= 3:
                hierarchy[f'title_{level}'] = title
                for j in range(level+1, 7):
                    hierarchy[f'title_{j}'] = None
                    hierarchy[f'tags_under_title_{j}'] = None
        else:
            is_title_line = False
        if is_title_line:
            continue

        if is_note_metadata_block and is_local_metadata_block:
            raise ValueError(f'Erreur dans la lecture : à la fois block metadata local et global (ligne numéro {i+1} : {line})')

        elif is_note_metadata_block:
            parsed_key, parsed_value = parse_text_as_dict(line)
            json_content['Note metadata'].append({parsed_key: parsed_value})

        elif is_local_metadata_block:
            parsed_key, parsed_value = parse_text_as_dict(line)

            if parsed_key == 'tags':
                if parsed_value[0] != "[" or parsed_value[-1] != "]":
                    raise ValueError(f'La métadonnée locale est erronnée : format non type ARRAY (ligne numéro {i+1} : {line})')
                local_metadata_tags = set()
                parsed_tags = parsed_value.strip('[]').split(',')
                for tag in parsed_tags:
                    local_metadata_tags.add(tag.strip())
            
            hierarchy[f'tags_under_title_{current_title_level}'] = local_metadata_tags
        
        else:
            append_new = True
            project = hierarchy["project"]
            subject = hierarchy["subject"]
            tags = set()
            if hierarchy['tags_under_project'] is not None:
                tags = tags.union(hierarchy['tags_under_project'])
            if hierarchy['tags_under_subject'] is not None:
                tags = tags.union(hierarchy['tags_under_subject'])
            for j in range(3, 7):
                if hierarchy[f'title_{j}'] is not None:
                    tags.add(hierarchy[f'title_{j}'])
                if hierarchy[f'tags_under_title_{j}'] is not None:
                    tags = tags.union(hierarchy[f'tags_under_title_{j}'])

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
    
    return json_content

def insert_noteparts_in_table(file):
    return
