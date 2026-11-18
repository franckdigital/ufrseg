from django.contrib import admin

from .models import AuthorEarning, Payment, Payout, Plan, RemunerationRule, RevenueSplit, Subscription

for m in (Plan, Subscription, Payment, Payout, RemunerationRule, RevenueSplit, AuthorEarning):
    admin.site.register(m)
