from django.db import models


class Note(models.Model):
    date = models.DateField(unique=True)
    raw = models.TextField(blank=True, null=True)
    is_test = models.BooleanField(default=False)
    
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'{self.date}'

class NotePart(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE)
    project = models.CharField(max_length=50, blank=False, default=None)
    subject = models.CharField(max_length=50, blank=True, default=None)
    tags = models.CharField(max_length=50, blank=True, default=None)
    content = models.TextField(blank=False, default=None)

    def __str__(self):
        string_repr = str(self.project)
        if self.subject:
            string_repr = f'{string_repr}, {self.subject}'
        return f'{self.project}, {self.subject}'
