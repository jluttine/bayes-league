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
        views.view_league,
        name="view_league",
    ),
    path(
        "league/<slug:league_slug>/edit/",
        views.edit_league,
        name="edit_league",
    ),
    path(
        "league/<slug:league_slug>/players/",
        views.view_players,
        name="view_players",
    ),
    path(
        "league/<slug:league_slug>/players/<uuid:player_uuid>/",
        views.view_player,
        name="view_player",
    ),
    path(
        "league/<slug:league_slug>/players/<uuid:player_uuid>/edit/",
        views.edit_player,
        name="edit_player",
    ),
    path(
        "league/<slug:league_slug>/stages/add/",
        views.create_stage,
        name="create_stage",
    ),
    path(
        "league/<slug:league_slug>/stages/view/<slug:stage_slug>/",
        views.view_stage,
        name="view_stage",
    ),
    path(
        "league/<slug:league_slug>/matches/",
        views.view_matches,
        name="view_matches",
    ),
    path(
        "league/<slug:league_slug>/matches/add/",
        views.create_match,
        name="create_match",
    ),
    # path(
    #     "league/<slug:league_slug>/matches/<uuid:match_uuid>/",
    #     views.view_match,
    #     name="view_match",
    # ),
    path(
        "league/<slug:league_slug>/matches/<uuid:match_uuid>/edit/",
        views.edit_match,
        name="edit_match",
    ),
    path(
        "league/<slug:league_slug>/ranking/",
        views.view_ranking,
        name="view_ranking",
    ),
]
