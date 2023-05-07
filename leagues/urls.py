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
        "league/<slug:league_slug>/edit/",
        views.edit_league,
        name="edit_league",
    ),
    path(
        "league/<slug:league_slug>/players/",
        views.show_league_players,
        name="show_league_players",
    ),
    path(
        "league/<slug:league_slug>/players/<uuid:player_uuid>/",
        views.player,
        name="player",
    ),
    path(
        "league/<slug:league_slug>/players/<uuid:player_uuid>/edit/",
        views.edit_player,
        name="edit_player",
    ),
    path(
        "league/<slug:league_slug>/matches/",
        views.league_matches,
        name="league_matches",
    ),
    path(
        "league/<slug:league_slug>/matches/add/",
        views.add_match,
        name="add_match",
    ),
    path(
        "league/<slug:league_slug>/matches/<uuid:match_uuid>/",
        views.match,
        name="match",
    ),
]
