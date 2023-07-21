from django.shortcuts import render, get_object_or_404
from django import http
from django.urls import reverse
from django.forms import inlineformset_factory
from django.conf import settings

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


def view_league(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    return render(
        request,
        "leagues/view_league.html",
        dict(
            league=league,
            ranking=league.ranking_set.last(),
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
        redirect=lambda **_: reverse(
            "view_league",
            args=[league_slug],
        ),
    )


def view_players(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    return form_view(
        request,
        forms.PlayerForm,
        template="leagues/view_players.html",
        redirect=lambda **_: reverse(
            "view_players",
            args=[league_slug],
        ),
        context=dict(
            league=league,
        ),
        instance=models.Player(league=league),
    )


def view_matches(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    return render(
        request,
        "leagues/view_matches.html",
        dict(
            league=league,
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
        )
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


def update_ranking(league):
    ms = (
        models.Match.objects.with_total_points()
        .prefetch_related("home_team")
        .prefetch_related("away_team")
        .filter(league=league)
    )
    ps = models.Player.objects.filter(league=league)
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
                # prefetch_related above.
                [p2id[p.uuid] for p in m.home_team.all()],
                [p2id[p.uuid] for p in m.away_team.all()],
                m.total_home_points,
                m.total_away_points,
            )
            for m in ms
            if m.total_home_points is not None
        ],
        len(p2id),
    )
    rnk = models.Ranking(league=league)
    rnk.save()
    models.RankingScore.objects.bulk_create(
        [
            models.RankingScore(
                ranking=rnk,
                player=ps[i],
                score=r,
            )
            for (i, r) in enumerate(rs)
        ]
    )
    return reverse(
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
        )
    )


def create_match(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    match = models.Match(league=league)
    return form_view(
        request,
        forms.MatchForm,
        template="leagues/create_match.html",
        redirect=lambda **_: update_ranking(league),
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
    return form_view(
        request,
        forms.MatchForm,
        template="leagues/edit_match.html",
        redirect=lambda **_: update_ranking(league),
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


def view_ranking(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    ranking = league.ranking_set.last()
    return render(
        request,
        "leagues/view_ranking.html",
        dict(
            league=league,
            ranking=ranking,
        )
    )
