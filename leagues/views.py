import functools
from argparse import Namespace

from django.shortcuts import render, get_object_or_404
from django import http
from django.urls import reverse
from django.forms import inlineformset_factory
from django.conf import settings
from django.db.models import Q

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


def form_view(request, Form, template, redirect, context={}, save=True,
              InlineFormSet=DummyInlineFormSet, instance=None):

    if instance is None:
        instance = Form.Meta.model()

    if request.method == "POST":

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
            matches=league.match_set.with_total_points().order_by("stage", "-datetime"),
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
    return form_view(
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
    return form_view(
        request,
        forms.LeagueForm,
        template="leagues/edit_league.html",
        context=dict(
            league=league,
        ),
        instance=league,
        redirect=lambda **_: update_ranking(
            league,
            *league.stage_set.all(),
            redirect=reverse(
                "view_league",
                args=[league_slug],
            ),
        ),
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
    return form_view(
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
    player = get_object_or_404(models.Player, league__slug=league_slug, uuid=player_uuid)
    return form_view(
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
    return form_view(
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
    stage = get_object_or_404(models.Stage, league__slug=league_slug, slug=stage_slug)
    return form_view(
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
    return form_view(
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


def edit_match(request, league_slug, match_uuid):
    league = get_object_or_404(models.League, slug=league_slug)
    match = get_object_or_404(models.Match, league=league, uuid=match_uuid)
    old_stage = match.stage
    return form_view(
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
