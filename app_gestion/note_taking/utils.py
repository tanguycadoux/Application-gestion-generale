from .models import Note, NotePart, Project

from datetime import datetime, date
from pathlib import Path
import shutil
import re


def validate_date_format(date_text):
    try:
        date.fromisoformat(date_text)
    except ValueError:
        raise ValueError("Incorrect data format, should be YYYY-MM-DD")

def insert_note_in_table(file, force=False):
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

    parsed_note = parse_note_as_dict(note)
    if note_date != parsed_note['note metadata']['date']:
        raise ValueError('La date de la note n\'est pas cohérente.')
    note.save()
    
    insert_noteparts_in_table(note, parsed_note)

    return note

def insert_noteparts_in_table(note: Note, parsed_note) -> list[NotePart]:
    note_parts = []
    for note_part_raw in parsed_note['content']:
        content = '\n'.join(note_part_raw['content'])

        project, _ = Project.objects.get_or_create(
            name=note_part_raw['project'],
            defaults={'description': note_part_raw['project']}
        )

        note_part = NotePart(
            note=note,
            project=project,
            subject=note_part_raw['subject'],
            tags=note_part_raw['tags'],
            content=content,
        )

        note_part.save()
        note_parts.append(note_part)
    return note_parts

def parse_note_as_dict(note: Note) -> dict:
    def parse_text_as_dict(text):
        parsed_text = text.split(':')
        if len(parsed_text) != 2:
            raise ValueError(f'La métadonnée est erronnée : format non type DICT ({text})')
        
        parsed_key   = parsed_text[0].strip()
        parsed_value = parsed_text[1].strip()

        return parsed_key, parsed_value
    
    json_content = {
        'file date': note.date,
        'note metadata': {},
        'content': [],
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

        if not is_code_block:
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
        if m and not is_code_block:
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

        elif is_note_metadata_block and line != "":
            parsed_key, parsed_value = parse_text_as_dict(line)
            json_content['note metadata'][parsed_key] = parsed_value

        elif is_local_metadata_block and line != "":
            parsed_key, parsed_value = parse_text_as_dict(line)

            if parsed_key == 'tags':
                if parsed_value[0] != "[" or parsed_value[-1] != "]":
                    raise ValueError(f'La métadonnée locale est erronnée : format non type ARRAY (ligne numéro {i+1} : {line})')
                local_metadata_tags = set()
                parsed_tags = parsed_value.strip('[]').split(',')
                for tag in parsed_tags:
                    local_metadata_tags.add(tag.strip())
            
            match current_title_level:
                case 1:
                    hierarchy[f'tags_under_project'] = local_metadata_tags
                case 2:
                    hierarchy[f'tags_under_subject'] = local_metadata_tags
                case _:
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
            
            for json_line in json_content['content']:
                json_line_tags = set(json_line["tags"])
                if project == json_line["project"] and subject == json_line["subject"] and tags == json_line_tags:
                    append_new = False
                    json_line["content"].append(line)
                    break
            if append_new:
                json_content['content'].append({
                    "project": project,
                    "subject": subject,
                    "tags": list(tags),
                    "content": [line],
                })
    
    lines_to_remove = []
    for i, json_line in enumerate(json_content['content']):
        content_as_str = "".join(json_line["content"])
        if content_as_str.strip() == "":
            lines_to_remove.append(i)
    for i in reversed(lines_to_remove):
        json_content['content'].pop(i)
    
    for json_line in json_content['content']:
        while json_line['content'][0] == "":
            json_line['content'].pop(0)
        while json_line['content'][-1] == "":
            json_line['content'].pop(-1)
    
    return json_content
