from django.contrib import admin

from .models import League, Player, Match, Ranking, RankingScore, Stage, Period


class PeriodAdminInline(admin.TabularInline):
    model = Period


class MatchAdmin(admin.ModelAdmin):
    inlines = [
        PeriodAdminInline,
    ]


admin.site.register(League)
admin.site.register(Stage)
admin.site.register(Player)
admin.site.register(Match, MatchAdmin)
admin.site.register(Ranking)
admin.site.register(RankingScore)
