from django.contrib import admin

from . import models

for m in (models.Groupe, models.Devoir, models.Soumission, models.Evaluation, models.Question, models.Copie, models.Note):
    admin.site.register(m)
