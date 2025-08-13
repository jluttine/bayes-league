import functools
from itertools import cycle, chain, repeat, count
import logging
import datetime
import time
from argparse import Namespace
import re
import numpy as np

from django.shortcuts import render, get_object_or_404
from django import http
from django.urls import reverse
from django.forms import inlineformset_factory, formset_factory
from django.conf import settings
from django.db.models import Q, Count
from django.core import exceptions
from django.core.exceptions import PermissionDenied, MultipleObjectsReturned
from django.db import IntegrityError
from django.db.models.functions import Now
from django.core import serializers

from . import models
from . import forms
from . import ranking
from . import tournament


def is_admin(league, request):
    admin_key = request.session.get(league.slug, {}).get("admin", None)
    return (
        # Check None separately because we don't want to claim to be "admin"
        # user when there's no write key (although admin rights are granted)
        False if admin_key is None else
        admin_key == league.write_key
    )


def get_user(league, request):
    if is_admin(league, request):
        return "admin"

    user_and_key = request.session.get(league.slug, {}).get("user", "").split("/")

    try:
        (user, key) = user_and_key
    except ValueError:
        return None

    try:
        player = models.Player.objects.get(uuid=user, key=key)
    except (exceptions.ValidationError, models.Player.DoesNotExist):
        return None
    else:
        return player.uuid


def can_administrate(league, user):
    return (
        True if not league.write_protected else
        user == "admin"
    )


class DummyInlineFormSet():

    def __init__(self, *args, **kwargs):
        return

    def is_valid(self):
        return True

    def save(self):
        return


def model_form_view(request, Form, template, redirect, context={}, save=True,
                    InlineFormSet=DummyInlineFormSet, instance=None,
                    conditional=lambda post, process: process()):

    if instance is None:
        instance = Form.Meta.model()

    def initial_form(message=None):
        form = Form(instance=instance)
        if message is not None:
            form.message = message
        return render(
            request,
            template,
            dict(
                form=form,
                formset=InlineFormSet(instance=instance),
                **context,
            ),
        )

    if request.method == "POST":

        def process():
            form = Form(
                request.POST,
                instance=instance,
            )

            formset = InlineFormSet(request.POST, request.FILES, instance=form.instance)
            if form.is_valid():
                if formset.is_valid():
                    if save:
                        form.save()
                        formset.save()
                    return http.HttpResponseRedirect(redirect(**form.cleaned_data))
            elif any(
                    "modified" == e.code
                    for e in form.errors.as_data().get("__all__", [])
            ):
                # Special handling for the case when multiple people edited the
                # form at the same time.
                return initial_form(
                    message=(
                        "ERROR: Someone edited at the same time. "
                        "Your input was ignored. Please check if everything is "
                        "correct and modify again if needed. "
                        "Sorry for the inconvenience."
                    )
                )
            else:
                return render(
                    request,
                    template,
                    dict(
                        form=form,
                        formset=formset,
                        **context,
                    )
                )
        return conditional(request.POST, process)

    else:
        return initial_form()


def index(request):
    leagues = models.League.objects.all()
    return render(
        request,
        "leagues/index.html",
        dict(
            leagues=leagues,
            debug=settings.DEBUG,
        )
    )


def info(request, league_slug):
    # We don't actually use the league but because the league site is the whole
    # website, each league has this same site.
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    return render(
        request,
        "leagues/info.html",
        dict(
            league=league,
            user_player=user,
            can_administrate=can_administrate(league, user)
        ),
    )


def get_user_banner_matches(matches, league, user):
    return (
        {} if user is None or can_administrate(league, user) else
        dict(
            user_next_up=matches.filter(
                can_start=True,
                can_edit=True,
            ),
            user_ongoing=matches.filter(
                can_edit=True,
                period_count=0,
                datetime_started__isnull=False,
            ),
        )
    )


def view_league(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    next_up = league.next_up_matches()
    matches = league.match_set.with_total_points(user=user, next_up=next_up)
    return render(
        request,
        "leagues/view_league.html",
        dict(
            league=league,
            ranking=[
                Namespace(
                    player=p,
                    score=p.score,
                )
                for p in league.player_set.all().order_by("-score", "name")
            ],
            user_player=user,
            can_administrate=can_administrate(league, user),
            **get_user_banner_matches(matches, league, user),
            **models.group_matches(matches),
        )
    )


def create_league(request, league_slug):
    raise NotImplementedError()
    return model_form_view(
        request,
        forms.LeagueForm,
        template="leagues/create_league.html",
        context=dict(
            slug=league_slug,
        ),
        instance=models.League(slug=league_slug),
        redirect=lambda **_: reverse(
            "view_league",
            args=[league_slug],
        ),
    )


def edit_league(request, league_slug):

    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    if not can_administrate(league, user):
        raise PermissionDenied()

    def move(post, **movable_models):
        for key in post:
            for (model_name, (model, id_name)) in movable_models.items():
                m = re.fullmatch(
                    r"^move " + model_name + r" (?P<id>.*) (?P<action>(top|above|below|bottom)) ?(?P<arg>.+)?$",
                    key,
                )
                if m is None:
                    continue
                d = m.groupdict()
                action = d["action"]
                obj = get_object_or_404(
                    model,
                    league=league,
                    **{id_name: d["id"]},
                )
                arg = d.get("arg")
                other = (
                    None if arg is None else
                    get_object_or_404(
                        model,
                        league=league,
                        **{id_name: arg},
                    )
                )
                if action == "top":
                    obj.bottom()
                elif action == "bottom":
                    obj.top()
                elif action == "above" and other is not None:
                    obj.below(other)
                elif action == "below" and other is not None:
                    obj.above(other)
        return http.HttpResponseRedirect(
            reverse("edit_league", args=[league.slug])
        )

    stages = [None] + list(league.stage_set.all()) + [None]
    stages_triple = list(zip(stages[:-2], stages[1:-1], stages[2:]))

    courts = [None] + list(league.court_set.all()) + [None]
    courts_triple = list(zip(courts[:-2], courts[1:-1], courts[2:]))

    return model_form_view(
        request,
        forms.LeagueForm,
        template="leagues/edit_league.html",
        context=dict(
            league=league,
            stages_triple=stages_triple,
            courts_triple=courts_triple,
            login_url=request.build_absolute_uri(
                reverse("login_admin", args=[league.slug, league.write_key])
            ),
            choose_player_login_url=request.build_absolute_uri(
                reverse("choose_player_login", args=[league.slug, league.player_selection_key])
            ),
            home_url=request.build_absolute_uri(
                reverse("view_league", args=[league.slug])
            ),
            user_player=user,
            can_administrate=can_administrate(league, user)
        ),
        instance=league,
        redirect=lambda **_: update_ranking(
            league,
            *league.stage_set.all(),
            # Log in just to make sure we won't be locked out if we enabled
            # write protection.
            redirect=(
                reverse(
                    "login_admin",
                    args=[league.slug, league.write_key],
                ) if league.write_protected else
                reverse(
                    "view_league",
                    args=[league.slug],
                )
            ),
        ),
        conditional=lambda post, process: (
            process() if "title" in post else
            move(
                post,
                stage=(models.Stage, "slug"),
                court=(models.Court, "pk"),
            )
        )
    )


def view_dashboard(request, league_slug, template="leagues/view_dashboard.html"):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    next_up = league.next_up_matches()
    stages = league.stage_set.filter(on_dashboard=True)
    rankings = [
        (stage.name, stage.rankingscore_set.all())
        for stage in stages
    ]
    if len(rankings) == 0:
        # If no stages selected to dashboard, show overall ranking
        rankings = [
            (
                "",
                [
                    Namespace(
                        player=p,
                        score=p.score,
                    )
                    for p in league.player_set.all().order_by("-score", "name")
                ]
            )
        ]

    return render(
        request,
        template,
        dict(
            league=league,
            next_matches=league.match_set.with_total_points(next_up=next_up, user=user).filter(
                can_start=True,
            ).order_by("court", "order", "pk"),
            ongoing_matches=league.match_set.with_total_points(user=user, next_up=None).filter(
                period_count=0,
                datetime_started__isnull=False,
            ).order_by("court", "-datetime_started"),
            latest_matches=league.match_set.with_total_points(user=user, next_up=None).filter(
                period_count__gt=0,
            ).order_by("-datetime_last_period")[:league.latest_matches_count],
            ranking=rankings,
            user_player=user,
            can_administrate=can_administrate(league, user),
        )
    )


def get_dashboard_content(request, league_slug):
    return view_dashboard(
        request,
        league_slug,
        template="leagues/dashboard_content.html",
    )


def view_stats(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    return render(
        request,
        "leagues/view_stats.html",
        dict(
            league=league,
            matches=league.match_set.with_total_points(user=user, next_up=None),
            players=league.player_set.with_stats().order_by("-score", "name"),
            user_player=user,
            can_administrate=can_administrate(league, user),
        )
    )


def view_player(request, league_slug, player_uuid):
    player = get_object_or_404(models.Player, league__slug=league_slug, uuid=player_uuid)
    user = get_user(player.league, request)
    next_up = player.league.next_up_matches()
    matches = player.league.match_set.with_total_points(
        user=user,
        next_up=next_up,
        player=player,
    )
    return render(
        request,
        "leagues/view_player.html",
        dict(
            league=player.league,
            player=player,
            **get_user_banner_matches(
                matches=matches,
                league=player.league,
                user=user,
            ),
            **models.group_matches(matches),
            ranking_stats=models.RankingScore.objects.with_ranking_stats(player),
            user_player=user,
            can_administrate=can_administrate(player.league, user),
        )
    )


def create_player(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    if not can_administrate(league, user):
        raise PermissionDenied()

    player = models.Player(league=league)
    return model_form_view(
        request,
        forms.PlayerForm,
        template="leagues/create_player.html",
        redirect=lambda **_: reverse(
            "view_league",
            args=[league_slug],
        ),
        context=dict(
            league=player.league,
            player=player,
            user_player=user,
            can_administrate=True,
        ),
        instance=player,
    )


def edit_player(request, league_slug, player_uuid):

    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()

    player = get_object_or_404(models.Player, league=league, uuid=player_uuid)
    return model_form_view(
        request,
        forms.PlayerForm,
        template="leagues/edit_player.html",
        redirect=lambda **_: reverse(
            "view_player",
            args=[league_slug, player_uuid],
        ),
        context=dict(
            league=player.league,
            player=player,
            user_player=user,
            can_administrate=True,
        ),
        instance=player,
    )


def delete_player(request, league_slug, player_uuid):

    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()

    player = get_object_or_404(models.Player, league=league, uuid=player_uuid)

    if request.method == "POST":
        try:
            player.delete()
        except IntegrityError:
            pass
        else:
            return http.HttpResponseRedirect(
                reverse("view_league", args=[league.slug])
            )
    return render(
        request,
        "leagues/delete_player.html",
        dict(
            player=player,
            league=league,
            user_player=user,
            can_administrate=True,
        ),
    )

def calculate_ranking(matches, regularisation, initial=dict()):
    # FIXME: One should be able to avoid reading Player table because we only
    # need some keys to identify the players and such keys should be in Match
    # table already. Then, remove prefetch_related.
    ps = list(
        functools.reduce(
            lambda acc, m: acc.union(
                set(m.home_team.all())
            ).union(
                set(m.away_team.all())
            ),
            matches,
            set(),
        )
    )
    p2id = {
        p.uuid: i
        for (i, p) in enumerate(ps)
    }
    r0 = list(map(
        lambda r: np.nan if r is None else r,
        [initial.get(p.uuid) for p in ps]
    ))
    (rs, raws) = ranking.calculate_ranking(
        [
            (
                # FIXME: One should be able to avoid reading Player table
                # because we only need some keys to identify the players and
                # such keys should be in Match table already. Then, remove
                # prefetch_related.
                [p2id[p.uuid] for p in m.home_team.all()],
                [p2id[p.uuid] for p in m.away_team.all()],
                m.total_home_points + m.home_bonus,
                m.total_away_points + m.away_bonus,
            )
            for m in matches
            if m.total_home_points is not None
        ],
        len(p2id),
        regularisation,
        initial=r0,
    )
    return (ps, rs, raws)


def update_league_ranking(league):
    ms = (
        models.Match.objects.with_total_points(user=None, next_up=None)
        .prefetch_related("home_team")
        .prefetch_related("away_team")
        .filter(league=league)
    )
    (ps, rs, raws) = calculate_ranking(
        ms,
        league.regularisation,
        initial={
            p.uuid: p.score_raw
            for p in models.Player.objects.filter(league=league)
        },
    )

    # Find ranking scores for each player in the league
    prs = {p.uuid: r for (p, r) in zip(ps, rs)}
    praws = {p.uuid: raw for (p, raw) in zip(ps, raws)}
    players = models.Player.objects.filter(league=league)
    for p in players:
        # Update the score (if found) or set to null
        p.score = prs.get(p.uuid, None)
        p.score_raw = praws.get(p.uuid, None)
    # Update the database
    models.Player.objects.bulk_update(players, ["score", "score_raw"])
    return


def update_stage_ranking(stage, regularisation):
    if stage is None:
        return
    # Matches contained in the stage
    ms = (
        stage
        .get_matches(user=None)
        .prefetch_related("home_team")
        .prefetch_related("away_team")
    )
    (ps, rs, raws) = calculate_ranking(
        ms,
        regularisation,
        initial={
            r.player.uuid: r.score_raw
            for r in models.RankingScore.objects.filter(stage=stage)
        },
    )

    # NOTE: Perhaps deletion and creation could be combined by using bulk_create
    # with update_conflicts and update_fields. However, we would still need to
    # delete ranking scores that shouldn't exist anymore (e.g., a player was
    # removed from all matches of the stage).

    # Delete existing ranking
    models.RankingScore.objects.filter(stage=stage).delete()

    # Create new ranking
    models.RankingScore.objects.bulk_create(
        [
            models.RankingScore(
                stage=stage,
                player=p,
                score=r,
                score_raw=raw,
            )
            for (p, r, raw) in zip(ps, rs, raws)
        ]
    )

    return


def update_ranking(league, *stages, redirect=None):
    update_league_ranking(league)
    stages = set(stages).union(
        set([
            s
            for stage in stages
            if stage is not None
            for s in stage.stage_set.all()
        ])
    )

    for stage in stages:
        update_stage_ranking(stage, league.regularisation)
    return redirect if redirect is not None else reverse(
        "view_league",
        args=[league.slug],
    )


def create_stage(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    if not can_administrate(league, user):
        raise PermissionDenied()

    stage = models.Stage(league=league)
    return model_form_view(
        request,
        forms.StageForm,
        template="leagues/create_stage.html",
        redirect=lambda **_: reverse(
            "edit_league",
            args=[league_slug],
        ),
        context=dict(
            league=stage.league,
            stage=stage,
            user_player=user,
            can_administrate=True,
        ),
        instance=stage,
    )


def edit_stage(request, league_slug, stage_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()

    stage = get_object_or_404(models.Stage, league=league, slug=stage_slug)
    return model_form_view(
        request,
        forms.StageForm,
        template="leagues/edit_stage.html",
        redirect=lambda **_: update_ranking(
            stage.league,
            stage,
            redirect=reverse(
                "view_stage",
                args=[league.slug, stage.slug],
            ),
        ),
        context=dict(
            league=stage.league,
            stage=stage,
            user_player=user,
            can_administrate=True,
        ),
        instance=stage,
    )


def delete_stage(request, league_slug, stage_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()

    stage = get_object_or_404(models.Stage, league=league, slug=stage_slug)

    if request.method == "POST":
        stage.delete()
        return http.HttpResponseRedirect(
            reverse("view_league", args=[league.slug])
        )
    else:
        return render(
            request,
            "leagues/delete_stage.html",
            dict(
                stage=stage,
                league=league,
                user_player=user,
                can_administrate=True,
            ),
        )

def view_stage(request, league_slug, stage_slug):
    stage = get_object_or_404(
        models.Stage,
        league__slug=league_slug,
        slug=stage_slug,
    )
    user = get_user(stage.league, request)
    next_up = stage.league.next_up_matches()
    matches = stage.get_matches(user=user, next_up=next_up)
    return render(
        request,
        "leagues/view_stage.html",
        dict(
            league=stage.league,
            stage=stage,
            user_player=user,
            can_administrate=can_administrate(stage.league, user),
            **get_user_banner_matches(matches, stage.league, user),
            **models.group_matches(matches),
        )
    )


def create_court(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    if not can_administrate(league, user):
        raise PermissionDenied()

    court = models.Court(league=league)
    return model_form_view(
        request,
        forms.CourtForm,
        template="leagues/create_court.html",
        redirect=lambda **_: reverse(
            "edit_league",
            args=[league_slug],
        ),
        context=dict(
            league=league,
            court=court,
            user_player=user,
            can_administrate=True,
        ),
        instance=court,
    )


def edit_court(request, league_slug, court_pk):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()

    court = get_object_or_404(models.Court, league=league, pk=court_pk)
    return model_form_view(
        request,
        forms.CourtForm,
        template="leagues/edit_court.html",
        redirect=lambda **_: reverse(
            "edit_league",
            args=[league.slug],
        ),
        context=dict(
            league=court.league,
            court=court,
            user_player=user,
            can_administrate=True,
        ),
        instance=court,
    )


def delete_court(request, league_slug, court_pk):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()

    court = get_object_or_404(models.Court, league=league, pk=court_pk)

    if request.method == "POST":
        court.delete()
        return http.HttpResponseRedirect(
            reverse(
                "edit_league",
                args=[league.slug],
            ),
        )
    else:
        return render(
            request,
            "leagues/delete_court.html",
            dict(
                court=court,
                league=league,
                user_player=user,
                can_administrate=True,
            ),
        )


def create_match(request, league_slug, stage_slug=None):
    league = get_object_or_404(models.League, slug=league_slug)
    stage = (
        None if stage_slug is None else
        get_object_or_404(models.Stage, league=league, slug=stage_slug)
    )
    user = get_user(league, request)

    if not can_administrate(league, user):
        raise PermissionDenied()

    match = models.Match(league=league, stage=stage)
    return model_form_view(
        request,
        forms.MatchForm,
        template="leagues/edit_match.html",
        # FIXME: If the match has no result, there would be no need to update
        # the ranking, just add players with None rankings if they aren't yet
        # included in the ranking.
        redirect=lambda stage=None, **_: update_ranking(league, stage),
        context=dict(
            league=league,
            match=match,
            user_player=user,
            can_administrate=True,
        ),
        instance=match,
        InlineFormSet=inlineformset_factory(
            models.Match,
            models.Period,
            fields=["home_points", "away_points"],
            extra=(
                stage.periods_safe if stage is not None else
                league.periods
            ),
        ),
    )


def find_r2_cost_lowerbound(R2_masked):
    """Given a distance matrix find a lower bound for total pairing distance

    "Illegal" pairings should be marked with infs before calling this function.

    Then, taking into account only the legal pairings, we'll find the lower
    bound as follows:

    1. Find the nearest opponent for each player

    2. Order the players by how far their nearest opponents are

    3. Starting from the worst player (i.e., whose nearest opponent is
       furthest), add this distance to the total cost and remove this opponent's
       own entry (i.e., mark its nearest opponent distance with nan)

    4. For the remaining players, go back to step 3 unless it has been computed
       N/2 times already (i.e., as many times as there should be games)

    Explanation: As each player is going to play, the largest of the shortest
    distances cannot be avoided so it should be included in the total cost. To
    avoid computing the same distance twice, we remove that opponent's own row
    (even if that opponent was preferring some other player).

    So, in the end we have a set of N/2 players who aren't each others nearest
    opponents. As each of those player is going to play, their minimum distances
    will form a lower bound.

    Proof: Not absolutely sure if this is true. Try to proof this more
    rigorously. But in practice this gives a hell of a speed up! From 1min to
    2ms.

    """
    N = np.shape(R2_masked)[0]
    optimal_opponents = np.argmin(R2_masked, axis=-1)
    optimal_r2 = R2_masked[np.arange(N), optimal_opponents]
    # We'll go through R2 costs starting from the worst (largest)
    ordering = np.argsort(-optimal_r2)

    count = 0
    cost = 0
    for n in range(N):
        i = ordering[n]
        if np.isnan(optimal_r2[i]):
            continue
        else:
            j = optimal_opponents[i]
            optimal_r2[j] = np.nan
            cost += optimal_r2[i]
            count += 1
        if 2 * count >= N:
            break

    return cost


def create_even_matches(players, extra_matches=[], odd_player_plays=True):
    # Sort players based on ranking
    players = sorted(
        players,
        key=lambda p: -np.inf if p.score is None else p.score,
        reverse=True
    )

    # Get matches in which the given players have played against each other
    matches = models.Match.objects.with_players(players)

    # Create a mapping from the ID to a list index
    ijs = {p.id: i for (i, p) in enumerate(players)}

    # Construct a matrix which tells how many times home player i has played
    # against away player j
    N = len(players)
    C = np.zeros((N, N))
    for m in matches:
        for hp in m.home_players:
            i = ijs[hp.id]
            for ap in m.away_players:
                j = ijs[ap.id]
                C[i,j] += 1

    C_extra = np.zeros((N, N))
    for (hp, ap) in extra_matches:
        i = ijs[hp.id]
        j = ijs[ap.id]
        C_extra[i,j] += 1

    C = C + C_extra

    # We don't care about home vs away, so make the matrix symmetric
    C = C + C.T
    C_extra = C_extra + C_extra.T

    # Ranking difference cost as a matrix
    rankings = np.array([
        np.nan if p.score is None else p.score
        for p in players
    ])
    R2 = np.nan_to_num(
        (rankings[:, None] - rankings[None, :]) ** 2,
        nan=0,
    )

    # The beef: find match pairings

    # If there is an odd number of players, first add one match where the
    # left-out player plays against the player it prefers the most.
    if N % 2 == 0:
        odd_matches = []
        remaining_players = np.arange(N)
        odd_player = None
    else:
        if odd_player_plays:
            # Find the "odd" player: has played the least
            odd_player = np.lexsort(
                (
                    # 2nd criterion: worst ranking
                    np.array([-np.inf if p.score is None else p.score for p in players]),
                    # 1st criterion: least matches played, take into account
                    # extra matches only
                    np.sum(C_extra, axis=0),
                )
            )[0]
            # The odd player plays twice
            opponent = np.lexsort(
                (
                    # Secondary key: ranking difference
                    R2[odd_player],
                    # Primary key: match counts
                    C[odd_player],
                    # Pre key: not the odd player itself
                    np.arange(N) == odd_player,
                )
            )[0]
            odd_matches = [(opponent, odd_player)]
            if C_extra[opponent,:].sum() > C_extra[odd_player,:].sum():
                # If the odd player had played less, let them play more
                remaining_players = np.delete(np.arange(N), opponent)
            else:
                # Otherwise, let the opponent play more, because it's nicer to
                # let the one higher in the ranking to play more.
                remaining_players = np.delete(np.arange(N), odd_player)
        else:
            # Find the "odd" player: has played the most
            odd_player = np.lexsort(
                (
                    # 2nd criterion: worst ranking
                    np.array([-np.inf if p.score is None else p.score for p in players]),
                    # 1st criterion: most matches played, take into account
                    # extra matches only
                    -np.sum(C_extra, axis=0),
                )
            )[0]
            # The odd player doesn't play at all
            odd_matches = []
            remaining_players = np.delete(np.arange(N), odd_player)

    # Find the optimal by traversing all possible solutions recursively.
    # Criteria:
    #
    # 1. Play against teams you've played least against with:
    #
    #    - Minimize the sum of number of matches the teams have already played
    #      against each other.
    #
    # 2. Play against teams with similar ranking:
    #
    #    - Minimize the square sum of ranking score differences between the
    #      teams in each pair.
    #
    # The first criterion is primary, so the second criterion is relevant only
    # when there are multiple possibilities with the same minimum for criterion
    # one.

    start_time = time.monotonic()

    def find_optimal_pairings(ps, best_cost, current_cost):

        # Can't pair one or less teams, so stop here
        if len(ps) < 2:
            logging.info(f"Leaf node: {best_cost}, {current_cost}")
            return ([], current_cost)

        if len(ps) % 2 != 0:
            raise RuntimeError("Only even number of players supported")

        # If we can't find better solutions, we'll just return Nones. No need to
        # bother finding locally best solution from this branch if we won't be
        # globally best anyway.
        retval = (None, None)

        # Check if it's not possible even in theory to find better solutions,
        # stop immediately.
        #
        # Minimum match counts for each player if we allow the same
        # opponents to be chosen multiple times
        #
        # WRONG: This counts matches many times (counts N matches when after
        # pairing we have N/2 matches)
        #
        # C_lowerbound = np.sum(
        #     np.amin(
        #         # Add inf to diagonal so we ignore playing against themselves
        #         C[ps[:,None], ps[None,:]] + np.diag(np.full(len(ps), np.inf)),
        #         axis=-1,
        #     )
        # )
        #
        # This didn't work either, for some reason..
        #
        # C_lowerbound = find_r2_cost_lowerbound(
        #     C[ps[:,None], ps[None,:]] + np.diag(np.full(len(ps), np.inf)),
        # )
        C_lowerbound = 0
        # Simple lower bound: Minimum ranking difference costs are obtained by
        # pairing 1v2, 3vs4, 5vs6, etc
        #
        # R2_lowerbound = np.sum(R2[ps[0::2], ps[1::2]])
        #
        # However, that's not good enough when there are pairings with small
        # ranking differences but bad match counts. So, we need to find a lower
        # bound based on what's allowed by the match count constraint.
        R2_lowerbound = find_r2_cost_lowerbound(
            # Masked distance matrix. Illegal matches are marked with inf.
            np.where(
                # This isn't a good criterion when teams have already played
                # against each other. In that case, this doesn't really mask
                # anything out because it's the sum of counts that gets bad, not
                # the single element..
                C[ps[:,None],ps[None,:]] + current_cost[0] > best_cost[0],
                np.inf,
                R2[ps[:,None],ps[None,:]]
            ) + np.diag(np.full(len(ps), np.inf))
        )

        # Combine lowerbounds
        cost_lowerbound = (
            current_cost[0] + C_lowerbound,
            current_cost[1] + R2_lowerbound,
        )
        if cost_lowerbound >= best_cost:
            return retval

        p0 = ps[0]

        prefs = np.lexsort(
            [
                # Secondary key: ranking difference
                R2[p0, ps],
                # Primary key: match counts
                C[p0, ps],
                # Pre key: keep the player itself first
                np.arange(len(ps)) != 0,
            ]
        )
        for j in range(1, len(ps)):
            if best_cost < (np.inf, np.inf) and time.monotonic() - start_time > 3:
                logging.warning(
                    "Match pairing taking over 3s, stopping and using current solution"
                )
                break
            p1 = ps[prefs[j]]
            # Current cost at this depth
            current_cost_new = (
                current_cost[0] + C[p0, p1],
                current_cost[1] + R2[p0, p1],
            )
            if current_cost_new >= best_cost:
                # No need to examine this branch deeper if this branch is
                # already worse than the currently best solution
                continue

            # Go deeper!
            (proposal_matches, proposal_cost) = find_optimal_pairings(
                np.delete(ps, [0, prefs[j]]),
                best_cost,
                current_cost_new,
            )
            if proposal_matches is None:
                # This branch had no better solutions
                continue
            elif proposal_cost < best_cost:
                # Yey! We found a solution that is currently the best one found!
                best_cost = proposal_cost
                retval = (
                    [(p0, p1)] + proposal_matches,
                    proposal_cost,
                )

        return retval

    logging.info("Starting match pairing optimization")
    (matches, _) = find_optimal_pairings(
        remaining_players,
        (np.inf, np.inf),
        (0, 0),
    )
    logging.info("Match pairing optimization ended")

    if odd_player is not None and odd_player_plays:
        # Move the second match of the odd player to be the last match
        inds = [
            i
            # NOTE: The odd matches aren't yet in matches list
            for i in range(len(matches))
            if matches[i][0] == odd_player or matches[i][1] == odd_player
        ]
        if len(inds) > 0:
            i = inds[0]
            m = matches.pop(i)
            matches.append(m)

    # Convert the list indices to player objects
    return [
        (players[m[0]], players[m[1]])
        for m in odd_matches + matches
    ]


def create_multiple_matches(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    if not can_administrate(league, user):
        raise PermissionDenied()

    if request.method == "POST":

        # NOTE: If we are coming here from the confirmation phase, the request
        # contains data from the hidden fields for the first form.
        form = forms.BulkMatchForm(league, request.POST)

        if not form.is_valid():
            return render(
                request,
                "leagues/create_multiple_matches.html",
                dict(
                    form=form,
                    league=league,
                    user_player=user,
                    can_administrate=True,
                )
            )

        if "generate" in request.POST:

            players = form.cleaned_data["players"]
            m = len(players)
            courts = form.cleaned_data.get("courts", [None])
            n = len(courts)
            rounds = form.cleaned_data["rounds"]

            if form.cleaned_data["autofill_teams"]:
                matches = []
                for i in range(rounds):
                    matches = matches + create_even_matches(
                        players,
                        extra_matches=matches,
                        # At rounds 0, 2, 4, 6, ... the odd player plays twice.
                        odd_player_plays=((i % 2) == 0),
                    )
            else:
                matches = ((rounds * m) // 2) * [(None, None)]


            DummyMatchFormset = formset_factory(
                forms.create_simple_match_form(
                    players=players,
                    league=league,
                ),
                extra=0,
            )
            formset = DummyMatchFormset(
                initial=[
                    dict(
                        home_team=[p1],
                        away_team=[p2],
                        court=court,
                    )
                    for (court, (p1, p2)) in zip(
                            cycle(courts),
                            matches,
                    )
                ],
            )
            # Use the algorithm to create matches
            #
            # Show a page that lists the games and asks for confirmation
            # matches = [
            #     (p1, p2)
            #     for (p1, p2) in zip(players[0::2], players[1::2])
            # ]
            return render(
                request,
                "leagues/create_multiple_matches.html",
                dict(
                    form=form,
                    stage_form=forms.ChooseStageForm(league),
                    league=league,
                    formset=formset,
                    user_player=user,
                    can_administrate=True,
                )
            )

        elif "confirm" in request.POST:
            DummyMatchFormset = formset_factory(
                forms.create_simple_match_form(
                    players=form.cleaned_data["players"],
                    league=league,
                ),
                extra=0,
            )
            stage_form = forms.ChooseStageForm(league, request.POST)
            formset = DummyMatchFormset(request.POST, initial=[])
            for f in formset:
                f.instance.league = league
            if stage_form.is_valid():
                stage = stage_form.cleaned_data.get("stage")
                valid = True
                for f in formset:
                    f.instance.stage = stage
                    if not f.is_valid():
                        valid = False
                if valid:
                    for f in formset:
                        instance = f.save()

                    # FIXME: We wouldn't need to completely recalculate the
                    # ranking, just adding missing players with None ranking
                    # suffices.
                    update_ranking(league, stage)
                    # Redirect to the league page
                    return http.HttpResponseRedirect(
                        reverse("view_league", args=[league.slug])
                    )

            return render(
                request,
                "leagues/create_multiple_matches.html",
                dict(
                    form=form,
                    stage_form=stage_form,
                    league=league,
                    formset=formset,
                    user_player=user,
                    can_administrate=True,
                )
            )

        else:
            raise RuntimeError("Unknown form")


    else:
        form = forms.BulkMatchForm(league)
        return render(
            request,
            "leagues/create_multiple_matches.html",
            dict(
                form=form,
                league=league,
                user_player=user,
                can_administrate=True,
            ),
        )


def generate_tournament(request, league_slug):

    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    if not can_administrate(league, user):
        raise PermissionDenied()

    if request.method == "POST":

        if "generate" in request.POST:

            form = forms.TournamentForm(league, request.POST)

            if form.is_valid():
                players = list(form.cleaned_data["players"])
                special_player = form.cleaned_data["special_player"]

                if special_player is not None:
                    try:
                        players.remove(special_player)
                    except ValueError:
                        pass
                    players = [special_player] + players

                courts = min(
                    len(players) // (2 * form.cleaned_data["team_size"]),
                    form.cleaned_data["courts"],
                )

                ms = tournament.greedy(
                    len(players),
                    form.cleaned_data["team_size"],
                    courts=courts,
                    special_player_mode=(special_player is not None),
                )

                matches = [
                    (
                        # Home team
                        [p for (p, mi) in zip(players, m) if mi == 1],
                        # Away team
                        [p for (p, mi) in zip(players, m) if mi == -1],
                    )
                    for m in ms
                ]

                t0 = form.cleaned_data["datetime"]
                duration = form.cleaned_data["duration"]
                dt = (
                    datetime.timedelta(0)
                    if duration is None else
                    datetime.timedelta(minutes=duration)
                )

                DummyMatchFormset = formset_factory(forms.DummyMatchForm, extra=0)
                formset = DummyMatchFormset(
                    initial=[
                        dict(
                            datetime=(
                                None if t0 is None else
                                t0 + (i // courts) * dt
                            ),
                            home_team=home,
                            away_team=away,
                        )
                        for (i, (home, away)) in enumerate(matches)
                    ],
                )
                # Use the algorithm to create matches
                #
                # Show a page that lists the games and asks for confirmation
                # matches = [
                #     (p1, p2)
                #     for (p1, p2) in zip(players[0::2], players[1::2])
                # ]
                return render(
                    request,
                    "leagues/generate_tournament.html",
                    dict(
                        form=form,
                        stage_form=forms.ChooseStageForm(league),
                        league=league,
                        formset=formset,
                        user_player=user,
                        can_administrate=True,
                    )
                )
            return render(
                request,
                "leagues/generate_tournament.html",
                dict(
                    form=form,
                    league=league,
                    user_player=user,
                    can_administrate=True,
                )
            )

        elif "confirm" in request.POST:
            DummyMatchFormset = formset_factory(
                forms.create_simple_match_form(
                    players=models.Player.objects.filter(league=league),
                    league=league,
                ),
                extra=0,
            )
            stage_form = forms.ChooseStageForm(league, request.POST)
            formset = DummyMatchFormset(request.POST, initial=[])
            if stage_form.is_valid():
                stage = stage_form.cleaned_data["stage"]
                for f in formset:
                    f.instance.league = league
                    f.instance.stage = stage
                    if f.is_valid():
                        instance = f.save()
            # Redirect to the stage page
            return http.HttpResponseRedirect(
                reverse("view_league", args=[league.slug])
            )
        else:
            raise RuntimeError("Unknown form")

    else:
        form = forms.TournamentForm(league)
        return render(
            request,
            "leagues/generate_tournament.html",
            dict(
                form=form,
                league=league,
                user_player=user,
                can_administrate=True,
            ),
        )


def create_calibration_matches(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    if not can_administrate(league, user):
        raise PermissionDenied()

    if request.method == "POST":

        # NOTE: If we are coming here from the confirmation phase, the request
        # contains data from the hidden fields for the first form.
        #form = forms.BulkMatchForm(league, request.POST)
        players = models.Player.objects.filter(league=league)

        n = players.count()
        PlayerFormSet = formset_factory(
            forms.CalibrationPlayerSelectionForm,
            extra=n,
            max_num=n,
            absolute_max=n,
            validate_max=True,
            formset=forms.CalibrationPlayerSelectionFormSet,
        )
        player_formset = PlayerFormSet(
            request.POST,
            form_kwargs=dict(players=players),
            prefix="players",
        )

        form = forms.CalibrationForm(request.POST, league=league)

        if not player_formset.is_valid() or not form.is_valid():
            return render(
                request,
                "leagues/create_calibration_matches.html",
                dict(
                    form=form,
                    player_formset=player_formset,
                    league=league,
                    user_player=user,
                    can_administrate=True,
                )
            )

        if "generate" in request.POST:
            ps = [
                f.cleaned_data["player"]
                for f in player_formset.forms
                if f.has_changed()
            ]
            m = len(players)
            courts = form.cleaned_data.get("courts", [None])
            n = len(courts)

            matches = tournament.create_circular_pairing(ps)

            DummyMatchFormset = formset_factory(
                forms.create_simple_match_form(
                    players=players,
                    league=league,
                ),
                extra=0,
            )
            match_formset = DummyMatchFormset(
                initial=[
                    dict(
                        home_team=[p1],
                        away_team=[p2],
                        court=court,
                    )
                    for (court, (p1, p2)) in zip(
                            cycle(courts),
                            matches,
                    )
                ],
                prefix="matches",
            )
            # Use the algorithm to create matches
            #
            # Show a page that lists the games and asks for confirmation
            # matches = [
            #     (p1, p2)
            #     for (p1, p2) in zip(players[0::2], players[1::2])
            # ]
            return render(
                request,
                "leagues/create_calibration_matches.html",
                dict(
                    form=form,
                    player_formset=player_formset,
                    league=league,
                    match_formset=match_formset,
                    user_player=user,
                    can_administrate=True,
                )
            )

        elif "confirm" in request.POST:
            DummyMatchFormset = formset_factory(
                forms.create_simple_match_form(
                    players=players,
                    league=league,
                ),
                extra=0,
            )
            match_formset = DummyMatchFormset(
                request.POST,
                initial=[],
                prefix="matches",
            )
            for f in match_formset:
                f.instance.league = league
            stage = form.cleaned_data.get("stage")
            valid = True
            for f in match_formset:
                f.instance.stage = stage
                if not f.is_valid():
                    valid = False
            if valid:
                for f in match_formset:
                    instance = f.save()

                # FIXME: We wouldn't need to completely recalculate the
                # ranking, just adding missing players with None ranking
                # suffices.
                update_ranking(league, stage)
                # Redirect to the league page
                return http.HttpResponseRedirect(
                    reverse("view_league", args=[league.slug])
                )

            return render(
                request,
                "leagues/create_calibration_matches.html",
                dict(
                    form=form,
                    league=league,
                    player_formset=player_formset,
                    match_formset=match_formset,
                    user_player=user,
                    can_administrate=True,
                )
            )

        else:
            raise RuntimeError("Unknown form")


    else:
        PlayerFormSet = formset_factory(
            forms.CalibrationPlayerSelectionForm,
            extra=models.Player.objects.filter(league=league).count(),
            formset=forms.CalibrationPlayerSelectionFormSet,
        )
        player_formset = PlayerFormSet(
            form_kwargs=dict(
                players=models.Player.objects.filter(league=league),
            ),
            prefix="players",
        )
        form = forms.CalibrationForm(league=league)
        return render(
            request,
            "leagues/create_calibration_matches.html",
            dict(
                form=form,
                player_formset=player_formset,
                league=league,
                user_player=user,
                can_administrate=True,
            ),
        )


def view_match(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    next_up = league.next_up_matches()
    match = get_object_or_404(
        models.Match.objects.with_total_points(user=user, next_up=next_up),
        league=league,
        uuid=match_uuid,
    )
    return render(
        request,
        "leagues/view_match.html",
        dict(
            league=league,
            match=match,
            user_player=user,
            can_administrate=can_administrate(league, user),
        ),
    )


def start_match(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    # NOTE: We allow all users to mark matches as started
    m = models.Match.objects.filter(
        league__slug=league_slug,
        uuid=match_uuid,
        datetime_started=None,
    )

    if league.write_protected and user != "admin":
        m = m.filter(Q(home_team__uuid=user) | Q(away_team__uuid=user))

    m.update(datetime_started=Now())

    # Go back to where you came from
    return http.HttpResponseRedirect(
        request.META.get(
            'HTTP_REFERER',
            reverse("view_match", args=[league_slug, match_uuid]),
        )
    )


def cancel_start_match(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    m = models.Match.objects.filter(
        league__slug=league_slug,
        uuid=match_uuid,
    )

    if league.write_protected and user != "admin":
        m = m.filter(Q(home_team__uuid=user) | Q(away_team__uuid=user))

    m.update(datetime_started=None)

    # Go back to where you came from
    return http.HttpResponseRedirect(
        request.META.get(
            'HTTP_REFERER',
            reverse("view_match", args=[league_slug, match_uuid]),
        )
    )


def add_result(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    match = get_object_or_404(models.Match, league=league, uuid=match_uuid)
    user = get_user(league, request)

    if (
            league.write_protected and
            user != "admin" and
            not match.home_team.filter(uuid=user).exists() and
            not match.away_team.filter(uuid=user).exists()
    ):
        raise PermissionDenied()

    return model_form_view(
        request,
        forms.ResultForm,
        template="leagues/add_result.html",
        redirect=lambda **_: update_ranking(
            league,
            match.stage,
            redirect=reverse("view_match", args=[league_slug, match_uuid]),
        ),
        context=dict(
            league=league,
            match=match,
            user_player=user,
            can_administrate=can_administrate(league, user),
            editing=match.period_set.exists(),
        ),
        instance=match,
        InlineFormSet=inlineformset_factory(
            models.Match,
            models.Period,
            fields=["home_points", "away_points"],
            extra=(
                match.stage.periods_safe if match.stage is not None else
                league.periods
            ),
        ),
    )


def edit_match(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()
    match = get_object_or_404(models.Match, league=league, uuid=match_uuid)
    old_stage = match.stage
    return model_form_view(
        request,
        forms.MatchForm,
        template="leagues/edit_match.html",
        redirect=lambda stage=None, **_: update_ranking(league, old_stage, stage),
        context=dict(
            league=league,
            match=match,
            user_player=user,
            can_administrate=True,
        ),
        instance=match,
        InlineFormSet=inlineformset_factory(
            models.Match,
            models.Period,
            fields=["home_points", "away_points"],
            extra=(
                match.stage.periods_safe if match.stage is not None else
                league.periods
            ),
        ),
    )


def delete_match(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()
    match = get_object_or_404(models.Match, league=league, uuid=match_uuid)

    if request.method == "POST":
        stage = match.stage
        match.delete()
        update_ranking(league, stage)
        return http.HttpResponseRedirect(
            reverse("view_league", args=[league.slug])
        )
    else:
        return render(
            request,
            "leagues/delete_match.html",
            dict(
                match=match,
                league=league,
                user_player=user,
                can_administrate=True,
            ),
        )


def delete_all_unplayed_matches(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()

    if request.method == "POST":
        # Matches that haven't been started and don't have any results yet.
        matches = league.match_set.annotate(
            period_count=Count("period", distinct=True),
        ).filter(
            datetime_started=None,
            period_count=0,
        )
        stages = set(filter(None, (m.stage for m in matches)))
        matches.delete()
        update_ranking(league, *stages)
        return http.HttpResponseRedirect(
            reverse("edit_league", args=[league.slug])
        )
    else:
        return render(
            request,
            "leagues/delete_all_unplayed_matches.html",
            dict(
                league=league,
                user_player=user,
                can_administrate=True,
            ),
        )


def login_admin(request, league_slug, key):
    league = get_object_or_404(models.League, slug=league_slug)

    if league.write_protected:
        if key != league.write_key:
            raise PermissionDenied()
        request.session[league.slug] = {
            "admin": key
        }

    return http.HttpResponseRedirect(
        reverse("view_league", args=[league.slug])
    )


def login_player(request, league_slug, player_uuid, key):
    player = get_object_or_404(
        models.Player,
        league__slug=league_slug,
        uuid=player_uuid,
    )

    if player.league.write_protected:
        if key != player.key:
            raise PermissionDenied()
        request.session[league_slug] = {
            "user": f"{player.uuid}/{key}"
        }

    return http.HttpResponseRedirect(
        reverse("view_player", args=[league_slug, player.uuid])
    )


def choose_player_login(request, league_slug, key):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)

    if key != league.player_selection_key:
        raise PermissionDenied()

    return render(
        request,
        "leagues/choose_player_login.html",
        dict(
            league=league,
            user_player=user,
            can_administrate=can_administrate(league, user),
            players=league.player_set.order_by("name")
        ),
    )


def logout(request, league_slug):
    try:
        # NOTE: We need to assign to request.session dictionary, otherwise
        # Django doesn't notice it has been altered and it won't update the
        # session
        del request.session[league_slug]
    except KeyError:
        pass

    return http.HttpResponseRedirect(
        reverse("view_league", args=[league_slug])
    )


def export_league(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    if not can_administrate(league, user):
        raise PermissionDenied()

    objs = (
        [league] +
        list(models.Stage.objects.filter(league=league)) +
        list(models.Player.objects.filter(league=league)) +
        list(models.Court.objects.filter(league=league)) +
        list(models.Match.objects.filter(league=league)) +
        list(models.HomeTeamPlayer.objects.filter(player__league=league)) +
        list(models.AwayTeamPlayer.objects.filter(player__league=league)) +
        list(models.Period.objects.filter(match__league=league))
    )

    return http.HttpResponse(
        serializers.serialize(
            "json",
            objs,
            use_natural_foreign_keys=True,
            use_natural_primary_keys=True,
        ),
        headers={
            "Content-Type": "application/json",
            "Content-Disposition": f'attachment; filename="{league_slug}.json"',
        },
    )


def import_league(request):
    if not request.user.is_superuser:
        raise PermissionDenied()

    if request.method != "POST":
        form = forms.LeagueImportForm()
    else:
        form = forms.LeagueImportForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data["file"]

            objs = serializers.deserialize(
                "json",
                f,
                handle_forward_references=True,
            )
            # We need to handle deferred fields because Stages can refer other
            # Stages arbitrarily
            objs_with_deferred_fields = []

            # Because we are changing the league slug, and league slug is being
            # used as a reference key in many of the models and nested deep in
            # the model tree, let's just use a "global" variable to override any
            # league slug when importing
            slug = form.cleaned_data["slug"]
            token = models.LEAGUE_SLUG.set(form.cleaned_data["slug"])
            try:
                for obj in objs:
                    # Make sure that:
                    #
                    # 1) we create new models even if the model already existed with the same natural key
                    #
                    # 2) models without naturaly keys (e.g., periods) won't use PKs
                    #    but just create new periods
                    if hasattr(obj.object, "pk"):
                        obj.object.pk = None

                    if isinstance(obj.object, models.League):
                        obj.object.slug = slug

                    obj.save()
                    if obj.deferred_fields is not None:
                        objs_with_deferred_fields.append(obj)

                for obj in objs_with_deferred_fields:
                    obj.save_deferred_fields()
            finally:
                models.LEAGUE_SLUG.reset(token)

            # Update rankings
            league = models.League.objects.get(slug=slug)
            update_ranking(league, *models.Stage.objects.filter(league=league))
            return http.HttpResponseRedirect(reverse("index"))

    return render(
        request,
        "leagues/import_league.html",
        dict(
            form=form,
        ),
    )
