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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.court_set.exists():
            # Next-up count is based on the number of courts
            del self.fields["nextup_matches_count"]


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


class CourtForm(ModelForm):

    class Meta:
        model = models.Court
        fields = [
            # FIXME: Because league is excluded, unique together constraint
            # isn't validated and integrity error is raised instead.
            "name",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
                "Someone had modified the match at the same time.",
                code="modified",
            )
        return


class MatchForm(ModelForm):

    last_updated_constraint = DateTimeField(
        required=False,
        widget=HiddenInput(),
    )

    class Meta:
        model = models.Match
        fields = [
            "stage",
            "court",
            "datetime_started",
            "home_team",
            "away_team",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        league = self.instance.league

        # Don't show stage selection if there are no stages
        stages = self.fields["stage"].queryset.filter(league=league)
        if not stages.exists():
            del self.fields["stage"]
        else:
            self.fields["stage"].queryset = stages
            self.fields["stage"].required = True

        courts = self.fields["court"].queryset.filter(league=league)
        if not courts.exists():
            # Don't show court field if there are no courts
            del self.fields["court"]
        else:
            # Require court if there are courts. This requirement is only on UI
            # level. It's ok to have NULL courts.
            self.fields["court"].queryset = courts
            self.fields["court"].required = True

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
        if home is None:
            raise ValidationError("Choose at least one player in home team")
        if away is None:
            raise ValidationError("Choose at least one player in away team")
        if any(p.league != league for p in home):
            raise ValidationError(f"All home team players must be from league: {league.title}")
        if any(p.league != league for p in away):
            raise ValidationError(f"All away team players must be from league: {league.title}")
        homeset = set(p.uuid for p in home)
        awayset = set(p.uuid for p in away)
        if len(homeset) != len(awayset):
            raise ValidationError("Teams must have the same number of players")
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
        if not self.fields["stage"].queryset.exists():
            del self.fields["stage"]
        else:
            self.fields["stage"].required = True
        return


def create_simple_match_form(league, players):

    class DummyMatchForm(ModelForm):
        """A simple read-only inline form for a single match used in bulk match creation"""

        class Meta:
            model = models.Match
            fields = ["court", "home_team", "away_team"]

        clean = MatchForm.clean

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.fields["home_team"].queryset = players
            self.fields["away_team"].queryset = players
            self.fields["home_team"].required = True
            self.fields["away_team"].required = True

            self.fields["court"].queryset = models.Court.objects.filter(league=league)
            return

    return DummyMatchForm


class BulkMatchForm(Form):
    players = PlayerMultipleChoiceField(models.Player.objects.all())
    courts = ModelMultipleChoiceField(
        models.Court.objects.all()
    )
    rounds = IntegerField(
        min_value=1,
        max_value=10,
        initial=1,
    )
    autofill_teams = BooleanField(
        initial=True,
        required=False,
    )

    def __init__(self, league, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["players"].queryset = models.Player.objects.filter(league=league)
        self.fields["players"].initial = self.fields["players"].queryset
        self.fields["players"].required = True

        courts = models.Court.objects.filter(league=league)
        if courts.exists():
            self.fields["courts"].queryset = courts
            self.fields["courts"].initial = courts
            self.fields["courts"].required = True
        else:
            del self.fields["courts"]

        return

    def clean_players(self):
        ps = self.cleaned_data["players"]
        if len(ps) < 2:
            raise ValidationError(
                "At least two players must be selected"
            )
        return ps

    def clean(self):
        try:
            rounds = self.cleaned_data["rounds"]
            players = len(self.cleaned_data["players"])
        except KeyError:
            pass
        else:
            if (players * rounds) % 2 != 0:
                self.message = """
                    WARNING: Both the number of players and rounds was odd.
                    Therefore, one player will be assigned to one match more
                    than the other players. If this is not ok, please consider
                    choosing even number of rounds and/or players.
                """
        return self.cleaned_data


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
