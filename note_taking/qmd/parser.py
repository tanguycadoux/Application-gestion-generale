"""Analyse du contenu d'une note qmd en note parts."""

import re

from ..exceptions import NoteParseError


def parse_note_raw_file_as_dict(date, raw) -> dict:
    def parse_text_as_dict(text):
        parsed_text = text.split(":")
        if len(parsed_text) != 2:
            raise NoteParseError(
                f"La métadonnée est erronnée : format non type DICT ({text})"
            )

        parsed_key = parsed_text[0].strip()
        parsed_value = parsed_text[1].strip()

        return parsed_key, parsed_value

    json_content = {
        "file date": date,
        "note metadata": {},
        "content": [],
    }

    is_note_metadata_block = False
    is_local_metadata_block = False
    is_callout_block = False
    is_code_block = False
    is_title_line = False
    current_title_level = None
    hierarchy: dict[str, None | str | set] = {
        "project": None,
        "tags_under_project": None,
        "subject": None,
        "tags_under_subject": None,
    }
    for i in range(3, 7):
        hierarchy[f"title_{i}"] = None
        hierarchy[f"tags_under_title_{i}"] = None
    local_metadata_tags: set[str] = set()
    for i, line in enumerate(raw.split("\n")):
        line = line.strip()

        if not is_code_block:
            if line.strip() == "---":
                if i == 0:
                    is_note_metadata_block = True
                else:
                    is_note_metadata_block = False
                continue

            if line == r"::: {.metadata}":
                is_local_metadata_block = True
                continue

            if line[:18] == r"::: {.callout-note":
                is_callout_block = True
                continue

            if is_local_metadata_block and line == ":::":
                is_local_metadata_block = False
                continue

            if is_callout_block and line == ":::":
                is_callout_block = False
                continue

        if line[0:3] == "```":
            is_code_block = not (is_code_block)

        # Récupération des titres
        m = re.match(r"^(#+)\s+(.*)", line)
        if m and not (is_code_block or is_callout_block):
            is_title_line = True
            level = len(m.group(1))
            title = m.group(2).strip()
            current_title_level = level

            if level == 1:
                hierarchy["project"] = title
                hierarchy["tags_under_project"] = None
                hierarchy["subject"] = None
                hierarchy["tags_under_subject"] = None
                for j in range(3, 7):
                    hierarchy[f"title_{j}"] = None
                    hierarchy[f"tags_under_title_{j}"] = None
            elif level == 2:
                hierarchy["subject"] = title
                for j in range(3, 7):
                    hierarchy[f"title_{j}"] = None
                    hierarchy[f"tags_under_title_{j}"] = None
            elif level >= 3:
                hierarchy[f"title_{level}"] = title
                for j in range(level + 1, 7):
                    hierarchy[f"title_{j}"] = None
                    hierarchy[f"tags_under_title_{j}"] = None
        else:
            is_title_line = False
        if is_title_line:
            continue

        if is_note_metadata_block and is_local_metadata_block:
            raise NoteParseError(
                f"Erreur dans la lecture : à la fois block metadata local et global (ligne numéro {i + 1} : {line})"
            )

        elif is_note_metadata_block and line != "":
            parsed_key, parsed_value = parse_text_as_dict(line)
            json_content["note metadata"][parsed_key] = parsed_value

        elif is_local_metadata_block and line != "":
            parsed_key, parsed_value = parse_text_as_dict(line)

            if parsed_key == "tags":
                if parsed_value[0] != "[" or parsed_value[-1] != "]":
                    raise NoteParseError(
                        f"La métadonnée locale est erronnée : format non type ARRAY (ligne numéro {i + 1} : {line})"
                    )
                local_metadata_tags = set()
                parsed_tags = parsed_value.strip("[]").split(",")
                for tag in parsed_tags:
                    local_metadata_tags.add(tag.strip())

            match current_title_level:
                case 1:
                    hierarchy["tags_under_project"] = local_metadata_tags
                case 2:
                    hierarchy["tags_under_subject"] = local_metadata_tags
                case _:
                    hierarchy[f"tags_under_title_{current_title_level}"] = (
                        local_metadata_tags
                    )

        else:
            append_new = True
            project = hierarchy["project"]
            subject = hierarchy["subject"]
            tags: set[str] = set()
            if hierarchy["tags_under_project"] is not None:
                tags = tags.union(hierarchy["tags_under_project"])
            if hierarchy["tags_under_subject"] is not None:
                tags = tags.union(hierarchy["tags_under_subject"])
            for j in range(3, 7):
                title = hierarchy[f"title_{j}"]
                if isinstance(title, str):
                    tags.add(title)
                tags_under_title = hierarchy[f"tags_under_title_{j}"]
                if isinstance(tags_under_title, set):
                    tags = tags.union(tags_under_title)

            for json_line in json_content["content"]:
                json_line_tags = set(json_line["tags"])
                if (
                    project == json_line["project"]
                    and subject == json_line["subject"]
                    and tags == json_line_tags
                ):
                    append_new = False
                    json_line["content"].append(line)
                    break
            if append_new:
                json_content["content"].append(
                    {
                        "project": project,
                        "subject": subject,
                        "tags": list(tags),
                        "content": [line],
                    }
                )

    lines_to_remove = []
    for i, json_line in enumerate(json_content["content"]):
        content_as_str = "".join(json_line["content"])
        if content_as_str.strip() == "":
            lines_to_remove.append(i)
    for i in reversed(lines_to_remove):
        json_content["content"].pop(i)

    for json_line in json_content["content"]:
        while json_line["content"][0] == "":
            json_line["content"].pop(0)
        while json_line["content"][-1] == "":
            json_line["content"].pop(-1)

    return json_content
