from django.contrib import admin
from django.urls import reverse
from django.utils.safestring import mark_safe
from ordered_model.admin import OrderedModelAdmin

from .models import League, Player, Match, Stage, Period


class LeagueAdmin(admin.ModelAdmin):
    readonly_fields = ["public_link", "admin_link"]

    @admin.display(description="Public link")
    def public_link(self, instance):
        if instance.pk is None:
            return mark_safe("<i>(not created yet)</i>")
        url = reverse("view_league", args=[instance.slug])
        return mark_safe(f'<a href="{url}">{url}</a>')

    @admin.display(description="Admin link")
    def admin_link(self, instance):
        if instance.pk is None:
            return mark_safe("<i>(not created yet)</i>")
        url = reverse("login", args=[instance.slug, instance.write_key])
        return (
            mark_safe(f'<a href="{url}">{url}</a>')
            if instance.write_protected else
            mark_safe("<i>(not write-protected)</i>")
        )


class PeriodAdminInline(admin.TabularInline):
    model = Period


class MatchAdmin(admin.ModelAdmin):
    inlines = [
        PeriodAdminInline,
    ]


class StageAdmin(OrderedModelAdmin):
    list_display = ('name', 'move_up_down_links')


admin.site.register(League, LeagueAdmin)
admin.site.register(Stage, StageAdmin)
admin.site.register(Player)
admin.site.register(Match, MatchAdmin)
