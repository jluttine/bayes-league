from django.shortcuts import render, get_object_or_404
from django import http
from django.urls import reverse

from . import models
from . import forms


def form_view(request, Form, template, redirect, instance_kwargs={}, context={},
              save=True):
    if request.method == "POST":
        form = Form(
            request.POST,
            instance=Form.Meta.model(**instance_kwargs)
        )
        if form.is_valid():
            if save:
                form.save()
            return http.HttpResponseRedirect(redirect(**form.cleaned_data))
        else:
            return render(
                request,
                template,
                dict(
                    form=form,
                    **context,
                )
            )
    else:
        return render(
            request,
            template,
            dict(
                form=Form(),
                **context,
            ),
        )

def index(request):
    leagues = models.League.objects.all()
    return form_view(
        request,
        forms.SlugForm,
        template="leagues/index.html",
        redirect=lambda slug, **_: reverse("league", args=[slug]),
        instance_kwargs={},
        context=dict(
            leagues=leagues,
        ),
        save=False,
    )
    # if request.method == "POST":
    #     form = forms.SlugForm(request.POST)
    #     if form.is_valid():
    #         slug = form.cleaned_data["slug"]
    #         return http.HttpResponseRedirect(reverse("league",args=[slug]))
    #     else:
    #         return render(
    #             request,
    #             "leagues/index.html",
    #             dict(
    #                 form=form,
    #                 leagues=leagues,
    #             ),
    #         )
    # else:
    #     return render(
    #         request,
    #         "leagues/index.html",
    #         dict(
    #             form=forms.SlugForm(),
    #             leagues=leagues,
    #         ),
    #     )


def league(request, league_slug):
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
            instance_kwargs=dict(
                slug=league_slug,
            ),
            redirect=lambda **_: reverse(
                "league",
                args=[league_slug],
            ),
        )
        # if request.method == "POST":
        #     form = forms.LeagueForm(
        #         request.POST,
        #         instance=models.League(slug=league_slug),
        #     )
        #     if form.is_valid():
        #         # Create a new league based on the form
        #         form.save()
        #         return http.HttpResponseRedirect(reverse("league", args=[league_slug]))
        #     else:
        #         # Show errors for a form filled incorrectly
        #         return render(
        #             request,
        #             "leagues/create_league.html",
        #             dict(
        #                 slug=league_slug,
        #                 form=form,
        #             ),
        #         )
        # else:
        #     # Provide empty form for creating a new league
        #     return render(
        #         request,
        #         "leagues/create_league.html",
        #         dict(
        #             slug=league_slug,
        #             form=forms.LeagueForm(),
        #         ),
        #     )
    else:
        # Show existing league
        return render(
            request,
            "leagues/show_league.html",
            dict(
                league=league,
            )
        )


def show_league_players(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    return form_view(
        request,
        forms.PlayerForm,
        template="leagues/show_league_players.html",
        redirect=lambda **_: reverse(
            "show_league_players",
            args=[league_slug],
        ),
        context=dict(
            league=league,
        ),
        instance_kwargs=dict(
            league=league,
        ),
    )


def league_matches(request, league_slug):
    league = get_object_or_404(models.League, slug=league_slug)
    return form_view(
        request,
        forms.MatchForm,
        template="leagues/league_matches.html",
        redirect=lambda **_: reverse(
            "league_matches",
            args=[league_slug],
        ),
        context=dict(
            league=league,
        ),
        instance_kwargs=dict(
            league=league,
        ),
    )


def player(request, player_uuid):
    player = get_object_or_404(models.Player, uuid=player_uuid)
    return render(
        request,
        "leagues/player.html",
        dict(
            player=player,
        )
    )


def match(request, match_uuid):
    match = get_object_or_404(models.Match, uuid=match_uuid)
    return render(
        request,
        "leagues/match.html",
        dict(
            match=match,
        )
    )
