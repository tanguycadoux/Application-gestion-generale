from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, UpdateView

from .app_registry import dashboard_blocks, project_usages, section_renamers
from .exceptions import AppError
from .forms import ProjectEditForm, ProjectForm
from .models import Project, Section
from .section_tree import section_tree
from .sections import check_new_name, levels
from .suggestions import elsewhere_suggestions as find_elsewhere
from .suggestions import project_suggestions as find_projects
from .suggestions import section_suggestions as find_sections


def index(request):
    """Accueil général : les blocs que chaque app déclare (#233)."""
    blocks = [
        {
            "title": block.title,
            "html": render_to_string(block.template, block.context(), request),
        }
        for block in dashboard_blocks()
    ]
    return render(request, "core/index.html", {"blocks": blocks})


def alerts_gallery(request):
    """Galerie des alertes (#156) : toasts sans disparition et confirmation
    ouverte, pour juger leur rendu sans déclencher de vrais messages. Réservée au
    développement : l'adresse n'est déclarée qu'avec `DEBUG`, et la vue refuse
    aussi hors `DEBUG`, au cas où elle serait branchée autrement."""
    if not settings.DEBUG:
        raise Http404
    return render(request, "core/debug/alerts_gallery.html")


def with_usage(projects):
    """Projets annotés du nombre d'objets de chaque app qui les utilisent."""
    return projects.annotate(
        **{
            f"usage_{i}": Count(
                usage.lookup,
                distinct=True,
                filter=~usage.exclude if usage.exclude else Q(),
            )
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


def project_paths(request, pk):
    """L'arbre des chemins d'un projet, avec ce qui utilise chaque niveau (#299)."""
    project = get_object_or_404(Project, pk=pk)
    return render(
        request,
        "core/project_paths.html",
        {"project": project, "rows": section_tree(project)},
    )


@require_POST
def delete_section(request, pk, section_pk):
    """Supprime un niveau inutilisé, avec ses descendants (#299) ; un niveau que des
    notes ou des tâches utilisent, lui ou un descendant, est refusé : il se renomme."""
    project = get_object_or_404(Project, pk=pk)
    section = get_object_or_404(Section, pk=section_pk, project=project)
    row = next(row for row in section_tree(project) if row.section.pk == section.pk)
    if row.total:
        messages.error(
            request,
            f"Le niveau « {section.name} » est utilisé par {row.usage} : "
            "suppression impossible.",
        )
    else:
        section.delete()
        below = {0: "", 1: ", avec son sous-niveau"}.get(
            row.descendants, f", avec ses {row.descendants} sous-niveaux"
        )
        messages.success(request, f"Le niveau « {section.name} » est supprimé{below}.")
    return redirect("core:project_paths", pk=pk)


def rename_section(request, pk, section_pk):
    """Renommer un niveau de chemin, en trois temps (#299) : le nouveau nom, le bilan
    des titres à réécrire où l'on décoche ce qu'on garde, puis l'écriture.

    Le niveau est renommé en place si tous ses titres le sont (ses descendants et les
    tâches qui le portent le suivent) ; sinon l'ancien et le nouveau coexistent.
    """
    project = get_object_or_404(Project, pk=pk)
    section = get_object_or_404(Section, pk=section_pk, project=project)
    source = request.POST if request.method == "POST" else request.GET
    raw_name = source.get("name", "")
    new_name, error = check_new_name(section, raw_name) if raw_name else ("", "")
    context = {
        "project": project,
        "section": section,
        "chain": levels(section),
        "new_name": raw_name,
        "error": error,
    }
    if not raw_name or error:
        return render(request, "core/section_rename.html", context)

    renamers = section_renamers()
    path = levels(section)
    occurrences = [
        occurrence
        for renamer in renamers
        for occurrence in renamer.occurrences(project, path)
    ]
    if request.method != "POST":
        context.update(new_name=new_name, occurrences=occurrences)
        return render(request, "core/section_rename.html", context)

    chosen = request.POST.getlist("headings")
    try:
        with transaction.atomic():
            if {occurrence.key for occurrence in occurrences} <= set(chosen):
                # Tous renommés : le niveau l'est en place, avec ce qui le porte.
                section.name = new_name
                section.save(update_fields=["name"])
            report = [
                sentence
                for renamer in renamers
                for sentence in renamer.rename(project, path, new_name, chosen)
            ]
    except AppError as e:
        messages.error(request, str(e))
        return redirect(
            f"{reverse('core:section_rename', args=[pk, section_pk])}?name={new_name}"
        )
    messages.success(
        request,
        f"Le niveau « {path[-1]} » est renommé « {new_name} ». {' '.join(report)}".strip(),
    )
    return redirect("core:project_paths", pk=pk)


@require_GET
def project_suggestions(request):
    """Les projets, pour les suggestions de l'éditeur (#90) : `?q=` filtre par nom."""
    projects = find_projects(request.GET.get("q", ""))
    return JsonResponse(
        {"results": [{"name": p.name, "color": p.color} for p in projects]}
    )


@require_GET
def section_suggestions(request):
    """Les niveaux à proposer sous un titre, pour l'éditeur (#90, #91).

    `?project=`, `?path=` (« Réunion/Préparation », vide pour les premiers niveaux)
    et `?q=`. `results` : les niveaux sous ce chemin ; `elsewhere` : les noms de
    niveau des autres endroits (tous projets, tous rangs), seulement avec une saisie.
    """
    query = request.GET.get("q", "")
    sections = find_sections(
        request.GET.get("project", ""), request.GET.get("path", ""), query
    )
    elsewhere = find_elsewhere(query, [section.name for section in sections])
    return JsonResponse(
        {
            "results": [{"name": s.name} for s in sections],
            "elsewhere": [{"name": name, "where": where} for name, where in elsewhere],
        }
    )
