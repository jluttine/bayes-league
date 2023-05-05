from django.forms import ModelForm

from . import models


class SlugForm(ModelForm):

    class Meta:
        model = models.League
        fields = ["slug"]


class LeagueForm(ModelForm):

    class Meta:
        model = models.League
        fields = ["title"]


class PlayerForm(ModelForm):

    class Meta:
        model = models.Player
        fields = ["name"]


class MatchForm(ModelForm):

    class Meta:
        model = models.Match
        fields = ["home_team", "away_team"]
