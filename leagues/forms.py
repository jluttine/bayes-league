from django.forms import (
    Form,
    ModelForm,
    ModelMultipleChoiceField,
    ModelChoiceField,
    DateTimeField,
)
from django.core.exceptions import ValidationError
from django.utils import timezone

from . import models


class SlugForm(ModelForm):

    class Meta:
        model = models.League
        fields = ["slug"]


class LeagueForm(ModelForm):

    class Meta:
        model = models.League
        fields = [
            "title",
            "bonus",
            "points_to_win",
            "regularisation",
            "nextup_matches_count",
            "latest_matches_count",
            "dashboard_update_interval",
        ]


class PlayerForm(ModelForm):

    class Meta:
        model = models.Player
        fields = ["name", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.update(dict(
            autofocus=True,
        ))
        return


class PlayerMultipleChoiceField(ModelMultipleChoiceField):
    def label_from_instance(self, member):
        return f"{member.name}"


class StageForm(ModelForm):

    class Meta:
        model = models.Stage
        fields = ["name", "bonus", "points_to_win", "included"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        league = self.instance.league
        self.fields["included"].queryset = models.Stage.objects.exclude(
            pk=self.instance.pk
        ).filter(
            league=self.instance.league
        )
        self.fields['name'].widget.attrs.update(dict(
            autofocus=True,
        ))
        return


class ResultForm(ModelForm):

    class Meta:
        model = models.Match
        fields = []


class MatchForm(ModelForm):

    class Meta:
        model = models.Match
        fields = ["stage", "datetime_started", "home_team", "away_team"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        league = self.instance.league

        # Don't show stage selection if there are no stages
        stages = self.fields["stage"].queryset.filter(league=league)
        if not stages.exists():
            del self.fields["stage"]
        else:
            self.fields["stage"].queryset = stages

        # Don't show datetime started if the match hasn't been started
        if self.instance.datetime_started is None:
            del self.fields["datetime_started"]

        self.fields["home_team"] = PlayerMultipleChoiceField(
            queryset = models.Player.objects.filter(league=league)
        )
        self.fields["away_team"] = PlayerMultipleChoiceField(
            queryset = models.Player.objects.filter(league=league)
        )
        return

    def clean(self):
        # NOTE: These constraints can't be defined in Model Constraints because
        # the constraints depend on multiple tables. They can't be defined in
        # Model.clean because ManyToManyField isn't available there. So, they
        # need to be defined here. But note that this doesn't put the
        # constraints to the admin form!
        league = self.instance.league
        home = self.cleaned_data.get("home_team")
        away = self.cleaned_data.get("away_team")
        if any(p.league != league for p in home):
            raise ValidationError(f"All home team players must be from league: {league.title}")
        if any(p.league != league for p in away):
            raise ValidationError(f"All away team players must be from league: {league.title}")
        homeset = set(p.uuid for p in home)
        awayset = set(p.uuid for p in away)
        if not homeset.isdisjoint(awayset):
            raise ValidationError("Players are allowed to play only in one of the teams, not both")
        return


class ChooseStageForm(ModelForm):

    class Meta:
        model = models.Match
        fields = ["stage"]

    def __init__(self, league, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.league = league
        self.fields["stage"].queryset = self.fields["stage"].queryset.filter(
            league=league
        )
        return


class DummyMatchForm(ModelForm):
    """A simple read-only inline form for a single match used in bulk match creation"""

    class Meta:
        model = models.Match
        fields = ["home_team", "away_team"]

    clean = MatchForm.clean


class BulkMatchForm(Form):
    players = PlayerMultipleChoiceField(models.Player.objects.all())
    # datetime = DateTimeField(
    #     initial=lambda: (
    #         timezone.now()
    #         .astimezone(timezone.get_default_timezone())
    #         .strftime("%Y-%m-%d %H:%M")
    #     ),
    #     input_formats=["%Y-%m-%d %H:%M"],
    # )

    def __init__(self, league, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["players"].queryset = models.Player.objects.filter(league=league)
        self.fields["players"].initial = self.fields["players"].queryset
        #self.fields["datetime"].initial = timezone.now()
        return
