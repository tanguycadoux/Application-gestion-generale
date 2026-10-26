from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from .app_registry import home_links, project_usages
from .forms import ProjectEditForm, ProjectForm
from .models import Project


def index(request):
    return render(request, "core/index.html", {"home_links": home_links()})


def with_usage(projects):
    """Projets annotés du nombre d'objets de chaque app qui les utilisent."""
    return projects.annotate(
        **{
            f"usage_{i}": Count(usage.lookup, distinct=True)
            for i, usage in enumerate(project_usages())
        }
    )


def usage_text(project) -> str:
    """« 1 note et 2 tâches », sans la partie nulle ; vide si rien n'utilise le projet."""
    parts = [
        usage.text(count)
        for i, usage in enumerate(project_usages())
        if (count := getattr(project, f"usage_{i}"))
    ]
    return " et ".join(parts)


def projects(request):
    project_list = list(with_usage(Project.objects.all()))
    for project in project_list:
        project.usage = usage_text(project)
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
    usage = usage_text(project)
    if usage:
        messages.error(
            request, f"Le projet « {project.name} » est utilisé par {usage}."
        )
    else:
        project.delete()
        messages.success(request, f"Le projet « {project.name} » est supprimé.")
    return redirect("core:projects")
