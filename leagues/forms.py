from django.forms import (
    Form,
    ModelForm,
    ModelMultipleChoiceField,
    ModelChoiceField,
    DateTimeField,
    IntegerField,
    BooleanField,
    HiddenInput,
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
            "periods",
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
        fields = [
            "name",
            "bonus",
            "periods",
            "points_to_win",
            "on_dashboard",
            "included",
        ]

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

    last_updated_constraint = DateTimeField(
        required=False,
        widget=HiddenInput(),
    )

    class Meta:
        model = models.Match
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["last_updated_constraint"].initial = self.instance.last_updated
        return

    def clean(self):
        # NOTE: This doesn't provide atomic database-level guarantee that we
        # save only if the match hasn't been edited in the meanwhile. For that,
        # we should do something like:
        #
        #   filter(last_updated=last_updated).update(...)
        #
        # But let's leave that for later, because it's not easy to add while
        # using the built-in form/formset features.
        if self.instance.last_updated != self.cleaned_data.get("last_updated_constraint"):
            raise ValidationError(
                "Someone had modified the match at the same time. "
                "Please cancel and try again if needed."
            )
        return


class MatchForm(ModelForm):

    last_updated_constraint = DateTimeField(
        required=False,
        widget=HiddenInput(),
    )

    class Meta:
        model = models.Match
        fields = ["stage", "datetime", "datetime_started", "home_team", "away_team"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        league = self.instance.league

        # Don't show stage selection if there are no stages
        stages = self.fields["stage"].queryset.filter(league=league)
        if not stages.exists():
            del self.fields["stage"]
        else:
            self.fields["stage"].queryset = stages

        # Don't show scheduled time if the match has already been started or
        # finished
        if self.instance.pk is not None and (
                self.instance.datetime_started is not None or
                self.instance.period_set.count() > 0
        ):
            del self.fields["datetime"]

        # Don't show datetime started if the match hasn't been started
        if self.instance.datetime_started is None:
            del self.fields["datetime_started"]

        self.fields["home_team"] = PlayerMultipleChoiceField(
            queryset = models.Player.objects.filter(league=league)
        )
        self.fields["away_team"] = PlayerMultipleChoiceField(
            queryset = models.Player.objects.filter(league=league)
        )
        self.fields["last_updated_constraint"].initial = self.instance.last_updated
        return

    def clean(self):
        # NOTE: This doesn't provide atomic database-level guarantee that we
        # save only if the match hasn't been edited in the meanwhile. For that,
        # we should do something like:
        #
        #   filter(last_updated=last_updated).update(...)
        #
        # But let's leave that for later, because it's not easy to add while
        # using the built-in form/formset features.
        if self.instance.last_updated != self.cleaned_data.get("last_updated_constraint"):
            raise ValidationError(
                "Someone had modified the match at the same time. "
                "Please cancel and try again if needed."
            )

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
        fields = ["datetime", "home_team", "away_team"]

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


class TournamentForm(Form):
    players = PlayerMultipleChoiceField(models.Player.objects.all())
    special_player = ModelChoiceField(models.Player.objects.all(), required=False)
    team_size = IntegerField(initial=2, min_value=2)
    courts = IntegerField(initial=1, min_value=1)
    datetime = DateTimeField(
        initial=timezone.now(),
        label="Starting datetime of the first round",
        required=True,
    )
    duration = IntegerField(
        initial=1,
        min_value=0,
        label="Round duration",
        help_text="minutes between rounds",
        required=True,
    )

    def __init__(self, league, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["players"].queryset = models.Player.objects.filter(league=league)
        self.fields["players"].initial = self.fields["players"].queryset
        self.fields["special_player"].queryset = models.Player.objects.filter(league=league)
        return
