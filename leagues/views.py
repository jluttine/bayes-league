import functools
import logging
import time
from argparse import Namespace
import re
import numpy as np

from django.shortcuts import render, get_object_or_404
from django import http
from django.urls import reverse
from django.forms import inlineformset_factory, formset_factory
from django.conf import settings
from django.db.models import Q
from django.core import exceptions
from django.core.exceptions import PermissionDenied, MultipleObjectsReturned
from django.db import IntegrityError
from django.db.models.functions import Now

from . import models
from . import forms
from . import ranking


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
        return render(
            request,
            template,
            dict(
                form=Form(instance=instance),
                formset=InlineFormSet(instance=instance),
                **context,
            ),
        )


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


def view_league(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    return render(
        request,
        "leagues/view_league.html",
        dict(
            league=league,
            matches=league.match_set.with_total_points(user=user),
            ranking=[
                Namespace(
                    player=p,
                    score=p.score,
                )
                for p in league.player_set.all().order_by("-score", "name")
            ],
            user_player=user,
            can_administrate=can_administrate(league, user)
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

    def move_stage(post):
        for key in post:
            m = re.fullmatch(
                r"^move (?P<slug>.*) (?P<action>(top|above|below|bottom)) ?(?P<arg>.+)?$",
                key,
            )
            if m is None:
                continue
            d = m.groupdict()
            action = d["action"]
            stage = get_object_or_404(
                models.Stage,
                league=league,
                slug=d["slug"]
            )
            arg = d.get("arg")
            other = (
                None if arg is None else
                get_object_or_404(
                    models.Stage,
                    league=league,
                    slug=arg,
                )
            )
            if action == "top":
                stage.bottom()
            elif action == "bottom":
                stage.top()
            elif action == "above" and other is not None:
                stage.below(other)
            elif action == "below" and other is not None:
                stage.above(other)
        return http.HttpResponseRedirect(
            reverse("edit_league", args=[league.slug])
        )

    stages = [None] + list(league.stage_set.all()) + [None]
    stages_triple = list(zip(stages[:-2], stages[1:-1], stages[2:]))

    return model_form_view(
        request,
        forms.LeagueForm,
        template="leagues/edit_league.html",
        context=dict(
            league=league,
            stages_triple=stages_triple,
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
            move_stage(post)
        )
    )


def view_dashboard(request, league_slug, template="leagues/view_dashboard.html"):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    return render(
        request,
        template,
        dict(
            league=league,
            next_matches=list(reversed(league.match_set.with_total_points(user=user).filter(
                period_count=0,
                datetime_started__isnull=True,
            ).order_by("datetime")[:league.nextup_matches_count])),
            ongoing_matches=league.match_set.with_total_points(user=user).filter(
                period_count=0,
                datetime_started__isnull=False,
            ).order_by("-datetime_started"),
            latest_matches=league.match_set.with_total_points(user=user).filter(
                period_count__gt=0,
            ).order_by("-datetime_last_period")[:league.latest_matches_count],
            ranking=[
                Namespace(
                    player=p,
                    score=p.score,
                )
                for p in league.player_set.all().order_by("-score", "name")
            ],
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
            matches=league.match_set.with_total_points(user=user),
            players=league.player_set.with_stats().order_by("-score", "name"),
            user_player=user,
            can_administrate=can_administrate(league, user),
        )
    )


def view_player(request, league_slug, player_uuid):
    player = get_object_or_404(models.Player, league__slug=league_slug, uuid=player_uuid)
    user = get_user(player.league, request)
    return render(
        request,
        "leagues/view_player.html",
        dict(
            league=player.league,
            player=player,
            matches=models.Match.objects.with_total_points(
                user=user,
                player=player,
            ),
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

def calculate_ranking(matches, regularisation):
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
    rs = ranking.calculate_ranking(
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
    )
    return (ps, rs)


def update_league_ranking(league):
    ms = (
        models.Match.objects.with_total_points(user=None)
        .prefetch_related("home_team")
        .prefetch_related("away_team")
        .filter(league=league)
    )
    (ps, rs) = calculate_ranking(ms, league.regularisation)

    # Find ranking scores for each player in the league
    prs = {p.uuid: r for (p, r) in zip(ps, rs)}
    players = models.Player.objects.filter(league=league)
    for p in players:
        # Update the score (if found) or set to null
        p.score = prs.get(p.uuid, None)
    # Update the database
    models.Player.objects.bulk_update(players, ["score"])
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
    (ps, rs) = calculate_ranking(ms, regularisation)

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
            )
            for (p, r) in zip(ps, rs)
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
    return render(
        request,
        "leagues/view_stage.html",
        dict(
            league=stage.league,
            stage=stage,
            matches=stage.get_matches(user=user),
            user_player=user,
            can_administrate=can_administrate(stage.league, user),
        )
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
            extra=3,
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


def create_even_matches(players):
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

    # We don't care about home vs away, so make the matrix symmetric
    C = C + C.T

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
    else:
        # Find the "odd" player
        odd_player = np.lexsort(
            (
                # 2nd criterion: worst ranking
                np.array([-np.inf if p.score is None else p.score for p in players]),
                # 1st criterion: least matches played
                np.sum(C, axis=0),
            )
        )[0]
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
        remaining_players = np.delete(np.arange(N), opponent)

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

        if "generate" in request.POST:

            form = forms.BulkMatchForm(league, request.POST)

            if form.is_valid():
                players = form.cleaned_data["players"]

                matches = create_even_matches(players)

                DummyMatchFormset = formset_factory(forms.DummyMatchForm, extra=0)
                formset = DummyMatchFormset(
                    initial=[
                        dict(
                            home_team=[p1],
                            away_team=[p2],
                        )
                        for (p1, p2) in matches
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

        elif "confirm" in request.POST:
            DummyMatchFormset = formset_factory(forms.DummyMatchForm, extra=0)
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


def view_match(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    user = get_user(league, request)
    match = get_object_or_404(
        models.Match.objects.with_total_points(user=user),
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
            extra=3,
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
            extra=3,
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
