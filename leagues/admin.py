from django.contrib import admin
from ordered_model.admin import OrderedModelAdmin

from .models import League, Player, Match, Stage, Period


class PeriodAdminInline(admin.TabularInline):
    model = Period


class MatchAdmin(admin.ModelAdmin):
    inlines = [
        PeriodAdminInline,
    ]


class StageAdmin(OrderedModelAdmin):
    list_display = ('name', 'move_up_down_links')


admin.site.register(League)
admin.site.register(Stage, StageAdmin)
admin.site.register(Player)
admin.site.register(Match, MatchAdmin)
