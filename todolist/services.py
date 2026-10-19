from .models import Todo, Project, Tag


def create_todo_from_dict(todo_data: dict) -> Todo:
    project, _ = Project.objects.get_or_create(name=todo_data["project"])

    todo, created = Todo.objects.get_or_create(
        created_from_note=True,
        note_part_date=todo_data["date"],
        note_part_text=todo_data["content"],
        defaults={
            "title": todo_data["content"],
            "project": project,
            "description": todo_data["description"],
            "due_date": todo_data["date"],
        },
    )

    if created:
        tag_names = todo_data.get("tags", [])

        if tag_names:
            tags = [
                Tag.objects.get_or_create(name=name)[0]
                for name in tag_names
            ]
            todo.tags.add(*tags)
    return todo
