from django.contrib import admin

from . import models

for m in (models.Annonce, models.Evenement, models.Notification, models.FAQ, models.ContactMessage, models.Offre):
    admin.site.register(m)
