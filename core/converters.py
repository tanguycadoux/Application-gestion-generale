"""Convertisseurs d'URL communs aux apps."""

from datetime import date

from django.urls import register_converter


class DateConverter:
    """Une date `AAAA-MM-JJ` : la date de la note identifie la note (#273).

    Une date impossible (`2026-02-30`) ne correspond à aucune route : 404.
    """

    regex = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"

    def to_python(self, value: str) -> date:
        return date.fromisoformat(value)

    def to_url(self, value: date | str) -> str:
        return value if isinstance(value, str) else value.isoformat()


register_converter(DateConverter, "date")
