from django.db import models


class Project(models.Model):
    name = models.CharField(unique=True, blank=False, null=False, max_length=50)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


class Note(models.Model):
    date = models.DateField(unique=True)
    raw = models.TextField(blank=True, null=True)
    is_test = models.BooleanField(default=False)
    tags = models.JSONField(null=True, blank=True)
    
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'{self.date}'
    
    @property
    def projects(self):
        return Project.objects.filter(
            note_parts__note=self
        ).distinct()

class NotePart(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="parts")
    project = models.ForeignKey(Project, on_delete=models.RESTRICT, related_name="note_parts")
    subject = models.CharField(max_length=50, blank=True, null=True, default=None)
    tags = models.JSONField(null=True, blank=True)
    content = models.TextField(blank=True, null=True, default=None)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        string_repr = str(self.project)
        if self.subject:
            string_repr = f'{string_repr}, {self.subject}'
        return f'{self.project}, {self.subject}'
