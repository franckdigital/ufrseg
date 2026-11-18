from django.contrib import admin

from .models import Candidature, Guide, Programme

admin.site.register(Guide)
admin.site.register(Programme)
admin.site.register(Candidature)
