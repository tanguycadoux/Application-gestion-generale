from django.db import models

import markdown
import re


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

    def rendered_content(self):
        def repl(match):
            pk = match.group("pk")
            alt = match.group("alt")
            attrs = match.group("attrs") or ""

            try:
                img = NotePartImage.objects.get(pk=pk)
                url = img.file.url
            except NotePartImage.DoesNotExist:
                url = "/static/img/image-missing.png"

            return f'![{alt}]({url}){attrs}'

        RENDER_IMAGE_REGEX = re.compile(
            r'\!\[(?P<alt>[^\]]*)\]\(image:(?P<pk>\d+)\)(?P<attrs>\{[^}]*\})?'
        )

        return markdown.markdown(RENDER_IMAGE_REGEX.sub(repl, self.content), extensions=["fenced_code", "tables"])    


class NotePartImage(models.Model):
    file = models.ImageField(upload_to="note_images/", blank=True, null=True)
    original_path = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.file.name
