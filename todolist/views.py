import json
from datetime import date

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    UpdateView,
)

from core.dates import date_text, parse_date_param
from core.month_calendar import requested_month
from core.sections import ancestors_and_self, forget_unused_sections
from note_taking.models import Note

from . import task_table, tree
from .forms import GoneLineFormSet, NoteReviewFormSet, TaskForm
from .gantt import gantt_chart
from .models import Task
from .services import (
    dismissed_rows,
    dismissed_subtree,
    note_lines,
    note_tasks_to_review,
    origin_anchor,
    removal_dismisses,
    remove_task,
    replace_task,
    restore_task,
    top_dismissed,
)
from .task_calendar import task_calendar
from .tree import TaskGroup, descendant_rows, task_groups, task_rows


def index(request):
    """Accueil : calendrier des tâches du mois demandé (?month=AAAA-MM), #167."""
    today, year, month = requested_month(request.GET.get("month", ""))
    return render(
        request,
        "todolist/index.html",
        {"calendar": task_calendar(year, month, today)},
    )


def task_list(request):
    """Tableau arborescent des tâches (#166) : un groupe par tâche racine.

    Tri (`?sort=due|title|progress`, `-` pour décroissant) et filtres dans l'URL
    (#178, `task_table.py`) : `?state=` (en cours par défaut, `done`, `all`,
    `dismissed`), `?title=`, `?project=`, `?path=<id>` (niveau et descendants,
    #298). Ce qui répond aux filtres reste affiché sous ses parents atténués.
    Les écartées (#290) ont leur tableau, avec les mêmes filtres.
    """
    state = task_table.read_state(request.GET)
    filters = task_table.task_filters(state)
    active = filters.read(request.GET)
    narrowed = any(key != "state" for key in active.values)
    context = {
        "filters": filters,
        "active_filters": active,
        "state": state,
        "state_label": task_table.STATE_LABELS[state],
        "narrowed": narrowed,
        "dismissed_count": top_dismissed().count(),
    }
    if state == task_table.DISMISSED:
        rows = dismissed_rows()
        if narrowed:
            kept = {t.pk for t in filters.apply([r.task for r in rows], active)}
            rows = [row for row in rows if row.task.pk in kept]
        for row in rows:
            # Les sous-tâches écartées sont rétablies avec elle : la confirmation le dit.
            row.confirm = f"Rétablir la tâche{with_subtasks(row.subtasks)} ?"
        context.update({"dismissed_rows": rows, "count": len(rows)})
    else:
        sort = tree.SORTING.read(request.GET.get("sort"))
        tasks = tree.load_tasks()
        matching = None
        if narrowed:
            matching = {t.pk for t in filters.apply(tasks, active)}
        done = {task_table.OPEN: False, task_table.DONE: True}.get(state)
        groups = task_groups(tasks, sort, matching, done)
        context.update(
            {
                "sorting": tree.SORTING,
                "sort": sort,
                "groups": groups,
                "count": sum(1 for g in groups for row in g.rows if not row.muted),
            }
        )
    return render(request, "todolist/task_list.html", context)


@require_POST
def restore_task_view(request, pk):
    """Rétablit une tâche écartée et ses sous-tâches écartées (#290)."""
    task = get_object_or_404(
        Task.all_objects, pk=pk, note_state=Task.NoteState.DISMISSED
    )
    subtasks = len(dismissed_subtree(task)) - 1
    dismissed_parent = restore_task(task)
    message = (
        f"La tâche « {task.title} »{with_subtasks(subtasks)} sont rétablies."
        if subtasks
        else f"La tâche « {task.title} » est rétablie."
    )
    if dismissed_parent:
        message += (
            f" Sa tâche parente « {dismissed_parent.title} » est écartée : "
            "elle est rétablie sans tâche parente."
        )
    messages.success(request, message)
    return redirect("todolist:task_list")


def with_subtasks(count: int) -> str:
    """« et sa sous-tâche », « et ses 3 sous-tâches », ou rien (#223)."""
    if count == 0:
        return ""
    return " et sa sous-tâche" if count == 1 else f" et ses {count} sous-tâches"


class TaskDetailView(DetailView):
    model = Task
    template_name = "todolist/task_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = self.object
        context["path"] = ancestors_and_self(task.section) if task.section else []
        origin_note = (
            Note.objects.filter(date=task.note_date).first()
            if task.created_from_note
            else None
        )
        context["origin_note"] = origin_note
        if origin_note:
            context["origin_anchor"] = origin_anchor(task, origin_note)
        context["children_groups"] = [TaskGroup(task, descendant_rows(task))]
        context["children"] = context["children_groups"][0].rows
        context["gantt"] = gantt_chart(task)
        # Les sous-tâches partent avec la tâche : la confirmation le dit (#223). Le titre
        # n'y figure pas : il peut être très long, et la page est celle de la tâche.
        # Un arbre qui contient une tâche issue d'une note est écarté (#290).
        subtasks = with_subtasks(len(context["children"]))
        context["dismisses"] = removal_dismisses(task)
        context["delete_confirm"] = (
            f"Écarter la tâche{subtasks} ? La section « Écartées » "
            "de la liste des tâches permet de revenir en arrière."
            if context["dismisses"]
            else f"Supprimer définitivement la tâche{subtasks} ?"
        )
        return context


class TaskCreateView(SuccessMessageMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "todolist/task_form.html"
    success_url = reverse_lazy("todolist:task_list")
    success_message = "La tâche « %(title)s » est créée."

    def get_initial(self):
        initial = super().get_initial()
        due = parse_date_param(self.request.GET.get("due", ""))
        if due:
            initial["due_date"] = due
        parent_id = self.request.GET.get("parent")
        if parent_id:
            try:
                parent = Task.objects.get(pk=parent_id)
                initial["parent"] = parent
                initial["project"] = parent.project
                initial["due_date"] = parent.due_date
            except Task.DoesNotExist:
                pass
        return initial


class TaskUpdateView(SuccessMessageMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "todolist/task_form.html"
    success_url = reverse_lazy("todolist:task_list")
    success_message = "La tâche « %(title)s » est modifiée."


class TaskDeleteView(SuccessMessageMixin, DeleteView):
    """Supprime ou écarte une tâche ; la confirmation se fait par popover HTML,
    dans la page de la tâche."""

    model = Task
    http_method_names = ["post"]
    success_url = reverse_lazy("todolist:task_list")

    def form_valid(self, form):
        # Compté avant la suppression, qui emporte les sous-tâches (#223).
        self.subtasks = self.object.descendants_count()
        success_url = self.get_success_url()
        # Un arbre qui contient une tâche issue d'une note est écarté (#240, #290).
        self.dismissed = removal_dismisses(self.object)
        remove_task(self.object)
        messages.success(self.request, self.get_success_message(form.cleaned_data))
        return HttpResponseRedirect(success_url)

    def get_success_message(self, cleaned_data):
        title = self.object.title
        removed = "écartée" if self.dismissed else "supprimée"
        if self.subtasks:
            return (
                f"La tâche « {title} »{with_subtasks(self.subtasks)} sont {removed}s."
            )
        return f"La tâche « {title} » est {removed}."


@require_GET
def parent_choices_view(request):
    """Choix de la tâche parente rechargé par htmx quand le projet, le chemin ou
    la case des terminées changent dans le formulaire d'une tâche (#390)."""
    task_id = request.GET.get("task", "")
    task = Task.objects.filter(pk=task_id).first() if task_id.isdigit() else None
    form = TaskForm(instance=task, parent_data=request.GET)
    return HttpResponse(str(form["parent"]))


@require_POST
def toggle_task(request, pk):
    task = get_object_or_404(Task, pk=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return JsonResponse({"error": "Corps de requête JSON invalide."}, status=400)

    completed = bool(data.get("completed"))
    if task.children.exists():
        # Un parent se coche à la main ; son avancement reste calculé (#164).
        task.done = completed
    else:
        # Décocher rend l'avancement d'avant la coche (#237).
        task.progress = 100 if completed else task.progress_before_done
    task.save()
    toggled_ids = [task.pk, *task.updated_ancestor_ids]
    # Lignes à jour, que la liste remplace sans recharger la page (#189).
    rows = {
        str(pk): render_to_string(
            "todolist/task_row.html", {"row": row}, request
        ).strip()
        for pk, row in task_rows(toggled_ids).items()
    }
    return JsonResponse({"status": "ok", "toggled_ids": toggled_ids, "rows": rows})


def note_review(request, note_date: date):
    """Bilan des tâches à revoir d'une note (#239, #240), puis retour à la note.

    - Tâches dont la ligne est dans la note (nouvelles, ou laissées « plus
      tard ») : échéance, priorité, projet et sujet se règlent aussitôt.
    - Tâches dont la ligne a disparu : la garder, l'écarter, ou la remplacer par
      la tâche d'une nouvelle ligne.

    Enregistrer les rend revues, sauf une tâche encore sans projet (texte sans
    projet de la note, #385) : elle reste à revoir. Sans tâche à revoir, retour
    direct à la note.
    """
    day = note_date
    note = get_object_or_404(Note, date=day)
    tasks = list(
        note_tasks_to_review(day).select_related("project", "section").order_by("pk")
    )
    if not tasks:
        return redirect("note_taking:note_detail", note_date=note.date)

    lines = note_lines(note.passages.prefetch_related("tags"))
    new_ids = [t.pk for t in tasks if (t.note_path, t.note_line_text) in lines]
    gone_ids = [t.pk for t in tasks if t.pk not in new_ids]
    new_tasks = Task.objects.filter(pk__in=new_ids).order_by("pk")
    data = request.POST or None
    new_formset = NoteReviewFormSet(data, queryset=new_tasks, prefix="new")
    gone_formset = GoneLineFormSet(
        data,
        queryset=Task.objects.filter(pk__in=gone_ids).order_by("pk"),
        prefix="gone",
        form_kwargs={"replacements": new_tasks},
    )

    if request.method == "POST" and new_formset.is_valid() and gone_formset.is_valid():
        # Une tâche nouvelle qui en remplace une autre disparaît : ses réglages
        # ne comptent pas, l'ancienne garde les siens.
        replaced = {
            form.cleaned_data["replacement"].pk
            for form in gone_formset
            if form.cleaned_data["action"] == "replace"
        }
        with transaction.atomic():
            for form in new_formset:
                if form.instance.pk not in replaced:
                    task = form.save(commit=False)
                    # Une tâche sans projet reste à revoir, jusqu'à ce qu'on lui
                    # en choisisse un (#385).
                    task.note_state = (
                        Task.NoteState.REVIEWED
                        if task.project_id
                        else Task.NoteState.TO_REVIEW
                    )
                    task.save()
            save_gone_lines(gone_formset)
        messages.success(
            request,
            f"Les tâches de la note du {date_text(day, 'moyen')} sont enregistrées.",
        )
        return redirect("note_taking:note_detail", note_date=note.date)
    return render(
        request,
        "todolist/note_review.html",
        {"note": note, "new_formset": new_formset, "gone_formset": gone_formset},
    )


def save_gone_lines(formset) -> None:
    """Applique le choix fait pour chaque tâche dont la ligne a disparu."""
    for form in formset:
        task, action = form.instance, form.cleaned_data["action"]
        if action == "keep":
            task.note_state = Task.NoteState.DETACHED
            task.save()
        elif action == "dismiss":
            remove_task(task)
        else:
            replace_task(task, form.cleaned_data["replacement"])
    # L'ancien niveau d'une tâche remplacée peut ne plus servir (#382).
    forget_unused_sections()
