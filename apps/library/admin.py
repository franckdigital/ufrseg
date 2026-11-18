from django.contrib import admin

from .models import Document, DocumentAccess, Favorite, Review


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("titre", "categorie", "statut", "auteur", "created")
    list_filter = ("categorie", "statut")
    search_fields = ("titre",)


admin.site.register(DocumentAccess)
admin.site.register(Favorite)
admin.site.register(Review)
