from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from .forms import ProjectEditForm, ProjectForm
from .models import Project


def index(request):
    return render(request, "core/index.html")


def count_text(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def usage_text(notes: int, tasks: int) -> str:
    """« 1 note et 2 tâches », sans la partie nulle ; vide si rien n'utilise le projet."""
    parts = []
    if notes:
        parts.append(count_text(notes, "note", "notes"))
    if tasks:
        parts.append(count_text(tasks, "tâche", "tâches"))
    return " et ".join(parts)


def with_usage(projects):
    """Projets annotés du nombre de notes et de tâches qui les utilisent."""
    return projects.annotate(
        notes_count=Count("note_parts__note", distinct=True),
        tasks_count=Count("todos", distinct=True),
    )


def projects(request):
    project_list = list(with_usage(Project.objects.all()))
    for project in project_list:
        project.usage = usage_text(project.notes_count, project.tasks_count)
        # Texte qui décrit le bouton de suppression désactivé (aria-describedby).
        project.usage_id = f"project-{project.pk}-usage"
    return render(request, "core/projects.html", {"projects": project_list})


class ProjectCreateView(SuccessMessageMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "core/project_form.html"
    success_url = reverse_lazy("core:projects")
    success_message = "Le projet « %(name)s » est créé."


class ProjectEditView(SuccessMessageMixin, UpdateView):
    model = Project
    form_class = ProjectEditForm
    template_name = "core/project_form.html"
    success_url = reverse_lazy("core:projects")

    def get_success_message(self, cleaned_data):
        return f"Le projet « {self.object.name} » est modifié."


@require_POST
def delete_project(request, pk):
    """Supprime un projet inutilisé ; un projet utilisé est refusé, avec la raison."""
    project = get_object_or_404(with_usage(Project.objects.all()), pk=pk)
    usage = usage_text(project.notes_count, project.tasks_count)
    if usage:
        messages.error(
            request, f"Le projet « {project.name} » est utilisé par {usage}."
        )
    else:
        project.delete()
        messages.success(request, f"Le projet « {project.name} » est supprimé.")
    return redirect("core:projects")
