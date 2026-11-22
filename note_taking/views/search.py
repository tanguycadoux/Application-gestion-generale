"""Page de recherche dans les notes (#199)."""

from dataclasses import replace

from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET

from core.path_tree import path_tree

from ..forms import NoteSearchForm
from ..search import (
    document_html,
    facet_counts,
    group_by_note,
    project_counts,
    result_options,
    search_note_parts,
    section_counts,
)
from ..search_paths import PathReport, path_reports
from ..search_query import SearchQuery, parse_query


@require_GET
def notes_search(request):
    """Recherche dans les notes (#199) : tout est dans l'adresse (`?q=…`), donc une
    recherche se partage, se garde en favori et survit au bouton retour.

    `results` vaut `None` tant qu'il n'y a rien à chercher (la page montre l'aide de
    syntaxe), et une liste, éventuellement vide, après une recherche. Les cases de
    projets et l'arbre des chemins (#302) s'ajoutent à la requête.

    L'arbre suit la requête (#380) : ses compteurs sont ceux du résultat sans les
    cases de l'arbre (sinon cocher un niveau mettrait les autres à 0), et les niveaux
    retenus par `chemin:` y sont marqués. Une réponse htmx ne remplace que les
    résultats, et les compteurs de l'arbre hors bande.
    """
    form = NoteSearchForm(request.GET or None)
    results = None
    query = SearchQuery()
    reports: list[PathReport] = []
    sections: list[int] = []
    projects: list[int] = []
    facets = None

    if form.is_bound and form.is_valid():
        query = parse_query(form.cleaned_data["q"])
        # Les niveaux retenus par chaque `chemin:`, ou de quoi corriger (#368).
        reports = path_reports(form.cleaned_data["q"])
        sections = [section.pk for section in form.cleaned_data["subjects"]]
        projects = [project.pk for project in form.cleaned_data["projects"]]
        results = search_note_parts(
            query,
            projects,
            sections,
            expand=not request.GET.get("exact"),
        )
        if query:
            unfiltered = (
                results
                if not (projects or sections)
                else search_note_parts(
                    replace(query, expansions=[]),
                    expand=not request.GET.get("exact"),
                )
            )
            facets = facet_counts(unfiltered or [])

    view, group = result_options(request.GET)
    as_document = bool(results) and view == "document"
    context = {
        "form": form,
        "results": results,
        "groups": group_by_note(query, results) if results and not as_document else [],
        "query": query,
        "path_reports": reports,
        "note_count": len({part.note_id for part in results or []}),
        "view": view,
        "group": group,
        "document": document_html(results, group) if as_document else None,
        "faceted": facets is not None,
    }
    used, project_used = section_counts(), project_counts()
    shown, project_shown = facets or (used, project_used)
    context["path_nodes"] = path_tree(
        shown,
        sections,
        only_counted=True,
        project_counts=project_shown,
        selected_projects=projects,
        used=used,
        project_used=project_used,
        marked={pk for r in reports if not r.negated for pk in r.section_ids},
    )
    if request.htmx:
        return HttpResponse(
            render_to_string("note_taking/notes_search_result.html", context, request)
        )
    return render(request, "note_taking/notes_search.html", context)
