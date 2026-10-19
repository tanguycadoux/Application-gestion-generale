from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.db.models import QuerySet


class Project(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Todo(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Basse'),
        ('medium', 'Moyenne'),
        ('high', 'Haute'),
    ]

    title = models.CharField(max_length=200)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="todos",
        null=True,
        blank=True,
    )
    tags = models.ManyToManyField(
        Tag,
        related_name="todos",
        blank=True
    )
    description = models.TextField(blank=True)
    completed = models.BooleanField(default=False)

    created_from_note = models.BooleanField(default=False)
    note_part_date = models.DateField(null=True, blank=True)
    note_part_text = models.CharField(max_length=200, blank=True, null=True)

    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium'
    )

    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )

    if TYPE_CHECKING:
        children: "QuerySet[Todo]"
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["created_from_note", "note_part_date", "note_part_text"],
                condition=Q(created_from_note=True),
                name="unique_note_parts_when_created_from_note",
            )
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if self.parent:
            ancestor = self.parent
            while ancestor:
                if ancestor == self:
                    raise ValidationError("Impossible de créer une boucle dans les sous-tâches.")
                ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        if self.parent:
            self.project = self.parent.project
            if not self.due_date:
                self.due_date = self.parent.due_date

        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def due_status(self):
        if not self.due_date or self.completed:
            return None

        today = date.today()
        delta = (self.due_date - today).days

        if delta < 0:
            return 'overdue'
        elif delta == 0:
            return 'today'
        elif delta <= 3:
            return 'soon'
        return 'normal'