from django.urls import path

from . import views


urlpatterns = [
    path(
        "",
        views.index,
        name="index",
    ),
    path(
        "league/<slug:league_slug>/",
        views.league,
        name="league",
    ),
    path(
        "league/<slug:league_slug>/players/",
        views.show_league_players,
        name="show_league_players",
    ),
    path(
        "league/<slug:league_slug>/matches/",
        views.league_matches,
        name="league_matches",
    ),
    path(
        "player/<uuid:player_uuid>/",
        views.player,
        name="player",
    ),
    path(
        "match/<uuid:match_uuid>/",
        views.match,
        name="match",
    ),
]
