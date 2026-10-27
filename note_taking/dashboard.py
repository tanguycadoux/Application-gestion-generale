"""Bloc « Note du jour » de l'accueil général (#233)."""

from django.utils import timezone

from .models import Note


def today_note() -> dict:
    today = timezone.localdate()
    return {"today": today, "note": Note.objects.filter(date=today).first()}
