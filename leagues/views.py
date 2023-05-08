from django.shortcuts import render, get_object_or_404
from django import http
from django.urls import reverse
from django.forms import inlineformset_factory

from . import models
from . import forms


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
    return form_view(
        request,
        forms.SlugForm,
        template="leagues/index.html",
        redirect=lambda slug, **_: reverse("view_league", args=[slug]),
        context=dict(
            leagues=leagues,
        ),
        save=False,
    )


def view_league(request, league_slug):
    try:
        league = models.League.objects.get(slug=league_slug)
    except models.League.DoesNotExist:
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
    else:
        # Show existing league
        return render(
            request,
            "leagues/view_league.html",
            dict(
                league=league,
            )
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
    return form_view(
        request,
        forms.MatchForm,
        template="leagues/view_matches.html",
        redirect=lambda **_: reverse(
            "view_matches",
            args=[league_slug],
        ),
        context=dict(
            league=league,
        ),
        instance=models.Match(league=league),
    )


def view_player(request, league_slug, player_uuid):
    player = get_object_or_404(models.Player, league__slug=league_slug, uuid=player_uuid)
    return render(
        request,
        "leagues/view_player.html",
        dict(
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
            player=player,
        ),
        instance=player,
    )

def create_match(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    match = models.Match(league=league)
    return form_view(
        request,
        forms.MatchForm,
        template="leagues/create_match.html",
        redirect=lambda **_: reverse(
            "view_matches",
            args=[league_slug],
        ),
        context=dict(
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
    match = get_object_or_404(models.Match, league__slug=league_slug, uuid=match_uuid)
    return form_view(
        request,
        forms.MatchForm,
        template="leagues/edit_match.html",
        redirect=lambda **_: reverse(
            "view_matches",
            args=[league_slug],
        ),
        context=dict(
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
