from .models import Note

from datetime import datetime, date
from pathlib import Path
import shutil


def copy_folder_contents(source_folder: str, dest_folder: str):
    source = Path(source_folder).expanduser().resolve()
    dest = Path(dest_folder).expanduser().resolve()

    if not source.exists() or not source.is_dir():
        raise ValueError(f"{source_folder} n'est pas un dossier valide.")

    dest.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)

def archive_folder(folder: str):
    source = Path(folder).expanduser().resolve()

    if not source.exists() or not source.is_dir():
        raise ValueError(f"{folder} n'est pas un dossier valide.")
    
    folder_timestamp = datetime.now().replace(microsecond=0).isoformat().replace(':', '-')

    dest = source.with_name(f'{source.name}_{folder_timestamp}')
    source.rename(dest)

def validate_date_format(date_text):
    try:
        date.fromisoformat(date_text)
    except ValueError:
        raise ValueError("Incorrect data format, should be YYYY-MM-DD")

def insert_note_in_table(filename: Path):
    note_date = filename.stem
    validate_date_format(note_date)
    note = Note(date=note_date)
    note.save()
    return note
