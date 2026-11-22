"""Classes Tailwind des cases du calendrier mensuel (#88, #167), communes aux apps.

La grille est dans core/month_calendar.py ; les balises `{% calendar_cell_classes %}`
et `{% calendar_number_classes %}` de `{% load ui %}` (core/templatetags/ui.py)
les appellent depuis le gabarit de case de chaque app.
"""


def calendar_cell_classes(day, inactive: bool = False, clickable: bool = True) -> str:
    """Classes d'une case du calendrier mensuel (#88, #167), communes aux apps.

    `inactive` : jour sans action possible (pointillés) ; `clickable` : la case
    entière est un lien (fond au survol).
    """
    classes = [
        "group relative flex h-full min-h-24 min-w-0 flex-col gap-1 rounded-lg border p-1.5"
    ]
    if inactive:
        classes.append("cursor-not-allowed border-dashed border-slate-300")
        classes.append("bg-slate-100" if day.is_weekend else "bg-transparent")
    else:
        classes.append("border-slate-200")
        if clickable:
            classes.append("hover:bg-blue-50")
        classes.append("bg-slate-100" if day.is_weekend else "bg-white")
    if not day.in_month:
        classes.append("opacity-40")
    if day.is_today:
        classes.append("ring-2 ring-blue-500")
    return " ".join(classes)


def calendar_number_classes(day, inactive: bool = False) -> str:
    """Classes du numéro d'un jour dans sa case."""
    if day.is_today:
        return "text-sm font-bold text-blue-800"
    if inactive:
        return "text-sm text-slate-300"
    if day.is_weekend:
        return "text-sm text-slate-400"
    return "text-sm text-slate-600"
