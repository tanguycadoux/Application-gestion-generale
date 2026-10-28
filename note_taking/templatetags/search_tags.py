from urllib.parse import urlencode

from django import template
from django.urls import reverse

from ..saved_searches import NAME_MAX_LENGTH, all_searches, search_url

register = template.Library()


@register.inclusion_tag("note_taking/saved_searches.html", takes_context=True)
def saved_searches(context, current_q=None) -> dict:
    """Les recherches enregistrées, et de quoi enregistrer la recherche en cours (#203).

    `current_q` : le texte de la zone de recherche. La balise charge elle-même la
    liste : la vue de la page n'a rien à lui passer.
    """
    q = (current_q or "").strip()
    suffix = f"?{urlencode({'q': q})}" if q else ""
    items = []
    for search in all_searches():
        rename_url = reverse("note_taking:saved_search_rename", args=[search.pk])
        delete_url = reverse("note_taking:saved_search_delete", args=[search.pk])
        items.append(
            {
                "search": search,
                "url": search_url(search),
                "current": bool(q) and search.q.strip() == q,
                "rename_action": rename_url + suffix,
                "delete_action": delete_url + suffix,
                "delete_id": f"delete-saved-search-{search.pk}",
            }
        )
    return {
        "items": items,
        "q": q,
        "default_name": q[:NAME_MAX_LENGTH],
        "name_max_length": NAME_MAX_LENGTH,
        "create_url": reverse("note_taking:saved_search_create"),
        "csrf_token": context.get("csrf_token", ""),
    }
