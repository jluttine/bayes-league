from django.urls import path

from . import views


urlpatterns = [
    path(
        "",
        views.index,
        name="index",
    ),
    path(
        "league/<slug:league_slug>/info/",
        views.info,
        name="info",
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
        "league/<slug:league_slug>/players/view/<uuid:player_uuid>/",
        views.view_player,
        name="view_player",
    ),
    path(
        "league/<slug:league_slug>/players/add/",
        views.create_player,
        name="create_player",
    ),
    path(
        "league/<slug:league_slug>/players/edit/<uuid:player_uuid>/",
        views.edit_player,
        name="edit_player",
    ),
    path(
        "league/<slug:league_slug>/players/delete/<uuid:player_uuid>/",
        views.delete_player,
        name="delete_player",
    ),
    path(
        "league/<slug:league_slug>/stages/add/",
        views.create_stage,
        name="create_stage",
    ),
    path(
        "league/<slug:league_slug>/stages/edit/<slug:stage_slug>/",
        views.edit_stage,
        name="edit_stage",
    ),
    path(
        "league/<slug:league_slug>/stages/delete/<slug:stage_slug>/",
        views.delete_stage,
        name="delete_stage",
    ),
    path(
        "league/<slug:league_slug>/stages/view/<slug:stage_slug>/",
        views.view_stage,
        name="view_stage",
    ),
    path(
        "league/<slug:league_slug>/matches/add/",
        views.create_match,
        name="create_match",
    ),
    path(
        "league/<slug:league_slug>/stages/add_match/<slug:stage_slug>/",
        views.create_match,
        name="create_match",
    ),
    path(
        "league/<slug:league_slug>/matches/bulk/",
        views.create_multiple_matches,
        name="create_multiple_matches",
    ),
    path(
        "league/<slug:league_slug>/matches/<uuid:match_uuid>/",
        views.view_match,
        name="view_match",
    ),
    path(
        "league/<slug:league_slug>/matches/<uuid:match_uuid>/start/",
        views.start_match,
        name="start_match",
    ),
    path(
        "league/<slug:league_slug>/matches/edit/<uuid:match_uuid>/",
        views.edit_match,
        name="edit_match",
    ),
    path(
        "league/<slug:league_slug>/matches/delete/<uuid:match_uuid>/",
        views.delete_match,
        name="delete_match",
    ),
    path(
        "league/<slug:league_slug>/login/<key>/",
        views.login,
        name="login",
    ),
    path(
        "league/<slug:league_slug>/logout/",
        views.logout,
        name="logout",
    ),
]
