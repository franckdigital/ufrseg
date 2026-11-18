from django.contrib import admin

from .models import ECUE, UE, AnneeAcademique, Classe, Filiere, Parcours, RegleValidation


class ECUEInline(admin.TabularInline):
    model = ECUE
    extra = 0


@admin.register(UE)
class UEAdmin(admin.ModelAdmin):
    list_display = ("code", "intitule", "niveau", "semestre", "credits", "type")
    list_filter = ("filiere", "niveau", "semestre")
    search_fields = ("code", "intitule")
    inlines = [ECUEInline]


for m in (AnneeAcademique, Filiere, Parcours, Classe, ECUE, RegleValidation):
    admin.site.register(m)
