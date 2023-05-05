from django.contrib import admin

from .models import League, Player, Match, Ranking, RankingScore


admin.site.register(League)
admin.site.register(Player)
admin.site.register(Match)
admin.site.register(Ranking)
admin.site.register(RankingScore)
