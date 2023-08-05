import functools
from argparse import Namespace
import re
import numpy as np

from django.shortcuts import render, get_object_or_404
from django import http
from django.urls import reverse
from django.forms import inlineformset_factory, formset_factory
from django.conf import settings
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError

from . import models
from . import forms
from . import ranking


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
    return render(
        request,
        "leagues/info.html",
        dict(
            league=league,
        ),
    )


def view_league(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    return render(
        request,
        "leagues/view_league.html",
        dict(
            league=league,
            matches=league.match_set.with_total_points(),
            ranking=[
                Namespace(
                    player=p,
                    score=p.score,
                )
                for p in league.player_set.all().order_by("-score")
            ],
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

    if league.write_protected and league_slug not in request.session.get("logins", []):
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
                reverse("login", args=[league.slug, league.write_key])
            ),
            home_url=request.build_absolute_uri(
                reverse("view_league", args=[league.slug])
            ),
        ),
        instance=league,
        redirect=lambda write_protected, **_: update_ranking(
            league,
            *league.stage_set.all(),
            # Log in just to make sure we won't be locked out if we enabled
            # write protection.
            redirect=(
                reverse(
                    "login",
                    args=[league.slug, league.write_key],
                ) if write_protected else
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


def view_player(request, league_slug, player_uuid):
    player = get_object_or_404(models.Player, league__slug=league_slug, uuid=player_uuid)
    return render(
        request,
        "leagues/view_player.html",
        dict(
            league=player.league,
            player=player,
            matches=models.Match.objects.with_total_points().filter(
                Q(home_team=player) | Q(away_team=player)
            )
        )
    )


def create_player(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
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
        ),
        instance=player,
    )


def edit_player(request, league_slug, player_uuid):

    league = get_object_or_404(models.League, slug=league_slug)
    if league.write_protected and league_slug not in request.session.get("logins", []):
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
        ),
        instance=player,
    )


def delete_player(request, league_slug, player_uuid):

    league = get_object_or_404(models.League, slug=league_slug)
    if league.write_protected and league_slug not in request.session.get("logins", []):
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
        ),
    )

def calculate_ranking(matches):
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
    )
    return (ps, rs)


def update_league_ranking(league):
    ms = (
        models.Match.objects.with_total_points()
        .prefetch_related("home_team")
        .prefetch_related("away_team")
        .filter(league=league)
    )
    (ps, rs) = calculate_ranking(ms)

    # Find ranking scores for each player in the league
    prs = {p.uuid: r for (p, r) in zip(ps, rs)}
    players = models.Player.objects.filter(league=league)
    for p in players:
        # Update the score (if found) or set to null
        p.score = prs.get(p.uuid, None)
    # Update the database
    models.Player.objects.bulk_update(players, ["score"])
    return


def update_stage_ranking(stage):
    if stage is None:
        return
    # Matches contained in the stage
    ms = (
        stage
        .get_matches()
        .prefetch_related("home_team")
        .prefetch_related("away_team")
    )
    (ps, rs) = calculate_ranking(ms)

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
        update_stage_ranking(stage)
    return redirect if redirect is not None else reverse(
        "view_league",
        args=[league.slug],
    )


def create_stage(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    stage = models.Stage(league=league)
    return model_form_view(
        request,
        forms.StageForm,
        template="leagues/create_stage.html",
        redirect=lambda **_: reverse(
            "view_league",
            args=[league_slug],
        ),
        context=dict(
            league=stage.league,
            stage=stage,
        ),
        instance=stage,
    )


def edit_stage(request, league_slug, stage_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    if league.write_protected and league_slug not in request.session.get("logins", []):
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
                args=[league_slug, stage_slug],
            ),
        ),
        context=dict(
            league=stage.league,
            stage=stage,
        ),
        instance=stage,
    )


def view_stage(request, league_slug, stage_slug):
    stage = get_object_or_404(
        models.Stage,
        league__slug=league_slug,
        slug=stage_slug,
    )
    return render(
        request,
        "leagues/view_stage.html",
        dict(
            league=stage.league,
            stage=stage,
            matches=stage.get_matches(),
        )
    )


def create_match(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    match = models.Match(league=league)
    return model_form_view(
        request,
        forms.MatchForm,
        template="leagues/create_match.html",
        redirect=lambda stage, **_: update_ranking(league, stage),
        context=dict(
            league=league,
            match=match,
        ),
        instance=match,
        InlineFormSet=inlineformset_factory(
            models.Match,
            models.Period,
            fields=["home_points", "away_points"],
            extra=3,
        ),
    )


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
        opponent = np.lexsort(
            (
                R2[-1,:-1], # secondary key: ranking difference
                C[-1,:-1], # primary key: match counts
            )
        )[0]
        odd_matches = [(opponent, N-1)]
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

    def find_optimal_pairings(ps, best_cost, current_cost):

        # Can't pair one or less teams, so stop here
        if len(ps) < 2:
            return ([], current_cost)

        # If we can't find better solutions, we'll just return Nones. No need to
        # bother finding locally best solution from this branch if we won't be
        # globally best anyway.
        retval = (None, None)

        p0 = ps[0]
        for j in range(1, len(ps)):
            p1 = ps[j]
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
                np.delete(ps, [0, j]),
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

    (matches, _) = find_optimal_pairings(
        remaining_players,
        (np.inf, np.inf),
        (0, 0),
    )

    # Convert the list indices to player objects
    return [
        (players[m[0]], players[m[1]])
        for m in odd_matches + matches
    ]


def create_multiple_matches(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)

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
                    )
                )
            return render(
                request,
                "leagues/create_multiple_matches.html",
                dict(
                    form=form,
                    league=league,
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
            ),
        )


def edit_match(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    if league.write_protected and league_slug not in request.session.get("logins", []):
        raise PermissionDenied()
    match = get_object_or_404(models.Match, league=league, uuid=match_uuid)
    old_stage = match.stage
    return model_form_view(
        request,
        forms.MatchForm,
        template="leagues/edit_match.html",
        redirect=lambda stage, **_: update_ranking(league, old_stage, stage),
        context=dict(
            league=league,
            match=match,
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
            ),
        )


def login(request, league_slug, key):
    league = get_object_or_404(models.League, slug=league_slug)

    if league.write_protected:
        if key != league.write_key:
            raise PermissionDenied()
        if league_slug not in request.session.get("logins", []):
            request.session["logins"] = request.session.get("logins", []) + [league_slug]

    return http.HttpResponseRedirect(
        reverse("view_league", args=[league.slug])
    )


def logout(request, league_slug):
    try:
        logins = request.session["logins"]
    except KeyError:
        pass
    else:
        # NOTE: We need to assign to request.session dictionary, otherwise
        # Django doesn't notice it has been altered and it won't update the
        # session
        request.session["logins"] = [
            x for x in request.session["logins"]
            if x != league_slug
        ]
    return http.HttpResponseRedirect(
        reverse("view_league", args=[league_slug])
    )
