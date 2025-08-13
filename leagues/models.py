import os
import uuid
import secrets
import contextvars

import numpy as np

from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from ordered_model.models import OrderedModel, OrderedModelManager

from . import ranking


LEAGUE_SLUG = contextvars.ContextVar("league_slug")


def create_key():
    # Read the dictionary of 2048 words (i.e., 11-bits of entropy per word)
    path = os.path.dirname(__file__)
    with open(os.path.join(path, "words.txt")) as f:
        words = f.readlines()
    # Choose four random words, so 44 bits of entropy. The longest word is 8
    # characters so this is at most 4x8+3x1=35 characters. Make sure the
    # relevant fields have proper max_length.
    key = '-'.join(secrets.choice(words).strip() for i in range(4))
    return key


class LeagueManager(models.Manager):
    def get_by_natural_key(self, slug):
        # Use the "global" league slug if defined so we can override the slug
        # that was in the imported file
        slug = LEAGUE_SLUG.get(slug)
        return self.get(slug=slug)


class League(models.Model):
    slug = models.SlugField(max_length=100, unique=True)
    title = models.CharField(max_length=100)
    bonus = models.PositiveIntegerField(default=0)
    periods = models.PositiveIntegerField(
        default=3,
        validators=[
            MinValueValidator(1),
        ],
    )
    points_to_win = models.PositiveIntegerField(default=21)
    regularisation = models.FloatField(
        default=1,
        validators=[MinValueValidator(0)]
    )
    nextup_matches_count = models.PositiveIntegerField(default=5)
    latest_matches_count = models.PositiveIntegerField(default=5)
    dashboard_update_interval = models.PositiveIntegerField(
        default=10,
        validators=[
            MinValueValidator(5),
        ]
    )
    write_protected = models.BooleanField(default=False)
    write_key = models.CharField(
        null=True,
        blank=True,
        default=None,
        max_length=50,
    )
    player_selection_key = models.CharField(
        null=True,
        blank=True,
        default=create_key,
        max_length=50,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    objects = LeagueManager()

    class Meta:
        ordering = ["title"]
        constraints = [
            # If the league is write-protected, it must have a write key
            models.CheckConstraint(
                check=(
                    models.Q(write_protected=False) |
                    models.Q(write_key__isnull=False)
                ),
                name="write_key_if_write_protected",
            ),
            models.CheckConstraint(
                check=models.Q(regularisation__gte=0),
                name="regularisation_gte_0",
            ),
        ]

    def natural_key(self):
        return (self.slug,)

    def clean(self):
        # Create a key when write-protection is enabled
        if self.write_key is None and self.write_protected:
            self.write_key = create_key()

        # Create a key when write-protection is enabled
        if self.player_selection_key is None and self.write_protected:
            self.player_selection_key = create_key()

        # NOTE: COMMENT OUT THE CODE BELOW. Let's not change the key every time
        # write-protection is re-enabled because we currently don't have any
        # means to log out all the other user sessions, so they'd stay logged in
        # although they logged in with an old key. We should revoke/expire those
        # sessions too.
        #
        # # Remove the key when write-protection is disabled
        # if not self.write_protected:
        #     self.write_key = None
        return

    def next_up_matches(self):
        courts = self.court_set.all()
        if courts.exists():
            # If all database backends supported "distinct on column", we could
            # just do:
            #
            # return self.match_set.with_period_count().filter(
            #     period_count=0,
            #     datetime_started__isnull=True,
            # ).order_by("order").distinct(
            #     "court",
            # )
            #
            # But as some backends don't support it, let's do it less
            # efficiently by querying for each court.
            next_up = self.match_set.with_period_count().filter(
                court=models.OuterRef("pk"),
                period_count=0,
                datetime_started__isnull=True,
            ).order_by("order").values("pk")[:1]
            cs = courts.annotate(
                next_up=models.Subquery(next_up),
            )
            return [c.next_up for c in cs] + list(
                self.match_set.with_period_count().filter(
                    court=None,
                    period_count=0,
                    datetime_started__isnull=True,
                ).order_by("order").values_list("pk", flat=True)[:1]
            )
        else:
            return self.match_set.with_period_count().filter(
                period_count=0,
                datetime_started__isnull=True,
            ).order_by("order")[:self.nextup_matches_count]

        # return self.match_set.with_period_count().filter(
        #     period_count=0,
        #     datetime_started__isnull=True,
        # # ).order_by("datetime", "pk").distinct(
        # #     "court",
        # # )[:self.nextup_matches_count]
        # ).order_by("datetime", "pk")[:self.nextup_matches_count]

    def __str__(self):
        return f"{self.title}"


class StageManager(OrderedModelManager):
    def get_by_natural_key(self, league_slug, stage_slug):
        return self.get(
            league__slug=LEAGUE_SLUG.get(league_slug),
            slug=stage_slug,
        )


class Stage(OrderedModel):
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        # Don't edit the league because otherwise existing stages might include
        # matches from different leagues
        editable=False,
    )
    name = models.CharField(
        max_length=50,
    )
    slug = models.SlugField()
    ranking = models.ManyToManyField(
        "Player",
        through="RankingScore",
    )
    included = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
    )
    periods = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=None,
        validators=[
            MinValueValidator(1),
        ],
    )
    points_to_win = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=None,
    )
    bonus = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=None,
    )
    # Whether to show the ranking of this stage in the dashboard
    on_dashboard = models.BooleanField(
        default=False,
    )

    objects = StageManager()

    class Meta:
        # The ordering is defined in OrderedModel base class
        ordering = [models.F("order").desc(nulls_first=True)]
        constraints = [
            models.UniqueConstraint(
                fields=["league", "slug"],
                name="unique_stage_slugs_in_league",
            ),
        ]

    def natural_key(self):
        return (self.league.slug, self.slug)

    natural_key.dependencies = ["leagues.league"]

    @property
    def periods_safe(self):
        return (
            self.periods if self.periods is not None else
            self.league.periods
        )

    def clean(self):
        self.slug = slugify(self.name)
        return

    def get_matches(self, user, next_up=None):
        return Match.objects.with_total_points(user, next_up=next_up).filter(
            models.Q(stage=self) |
            models.Q(stage__in=self.included.all())
        )

    def __str__(self):
        return self.name


class PlayerManager(models.Manager):

    def get_by_natural_key(self, league_slug, uuid):
        return self.get(
            league__slug=LEAGUE_SLUG.get(league_slug),
            uuid=uuid,
        )

    def with_stats(self):
        # NOTE: Each sum needs to be a separate subquery, otherwise the results
        # will be nonsense (Django issue, I suppose).
        home_points_won = self.annotate(
            home_points_won=(
                models.Sum("home_match_set__period__home_points", default=0)
            ),
        ).filter(pk=models.OuterRef("pk"))
        away_points_won = self.annotate(
            away_points_won=(
                models.Sum("away_match_set__period__away_points", default=0)
            ),
        ).filter(pk=models.OuterRef("pk"))
        home_points_lost = self.annotate(
            home_points_lost=(
                models.Sum("home_match_set__period__away_points", default=0)
            ),
        ).filter(pk=models.OuterRef("pk"))
        away_points_lost = self.annotate(
            away_points_lost=(
                models.Sum("away_match_set__period__home_points", default=0)
            ),
        ).filter(pk=models.OuterRef("pk"))
        return self.annotate(
            home_points_won=models.Subquery(home_points_won.values("home_points_won"), output_field=models.PositiveIntegerField()),
            away_points_won=models.Subquery(away_points_won.values("away_points_won"), output_field=models.PositiveIntegerField()),
            home_points_lost=models.Subquery(home_points_lost.values("home_points_lost"), output_field=models.PositiveIntegerField()),
            away_points_lost=models.Subquery(away_points_lost.values("away_points_lost"), output_field=models.PositiveIntegerField()),
            points_won=models.F("home_points_won") + models.F("away_points_won"),
            points_lost=models.F("home_points_lost") + models.F("away_points_lost"),
            points_played=models.F("points_won") + models.F("points_lost"),
            point_win_percentage=100.0 * models.F("points_won") / models.F("points_played")
        )


class Player(models.Model):

    objects = PlayerManager()

    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        # Don't edit the league because otherwise existing matches might include
        # players from different leagues
        editable=False,
    )
    name = models.CharField(
        max_length=50,
    )
    description = models.TextField(
        max_length=1000,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
    )
    score = models.FloatField(
        blank=True,
        null=True,
        default=None,
    )
    key = models.CharField(
        null=False,
        blank=False,
        default=create_key,
        max_length=50,
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            # In a league, all players have different names
            models.UniqueConstraint(
                fields=["league", "name"],
                name="unique_names_in_league",
            ),
            models.UniqueConstraint(
                fields=["league", "uuid"],
                name="unique_player_uuid_in_league",
            ),
        ]

    def natural_key(self):
        return (self.league.slug, self.uuid)

    natural_key.dependencies = ["leagues.league"]

    def current_ranking_stats(self):
        if self.score is None:
            return None
        ps = self.league.player_set.exclude(
            score__isnull=True,
        )
        count_above = ps.filter(score__gt=self.score).count()
        count_below = ps.filter(score__lt=self.score).count()
        aggs = ps.aggregate(
            count_total=models.Count("id"),
            score_minimum=models.Min("score"),
            score_maximum=models.Max("score"),
        )
        return dict(
            count_above=count_above,
            count_below=count_below,
            position=1+count_above,
            relative_position=100*(1-count_above/(aggs["count_total"]-1)),
            **aggs,
        )

    def __str__(self):
        return f"{self.name}"


def annotate_matches_with_period_count(matches):
    period_count = matches.annotate(
        period_count=models.Count("period", distinct=True),
    ).filter(pk=models.OuterRef("pk"))
    return matches.annotate(
        period_count=models.Subquery(
            period_count.values("period_count"),
            output_field=models.PositiveIntegerField(),
        ),
    )

def annotate_matches_with_periods(matches):
    home_periods = matches.filter(
        pk=models.OuterRef("pk"),
        period__home_points__gt=models.F("period__away_points"),
    ).annotate(
        home_periods=models.Count("period", distinct=True),
    )
    away_periods = matches.filter(
        pk=models.OuterRef("pk"),
        period__away_points__gt=models.F("period__home_points"),
    ).annotate(
        away_periods=models.Count("period", distinct=True),
    )
    return annotate_matches_with_period_count(matches).annotate(
        home_periods=models.functions.Coalesce(
            models.Subquery(
                home_periods.values("home_periods"),
                output_field=models.PositiveIntegerField(),
            ),
            0,
        ),
        away_periods=models.functions.Coalesce(
            models.Subquery(
                away_periods.values("away_periods"),
                output_field=models.PositiveIntegerField(),
            ),
            0,
        ),
    )


def group_matches(matches):
    """Group matches to upcoming, ongoing and finished

    .. note::

        The matches need to be sorted so that first are upcoming, then ongoing
        and then finished matches.

    """
    upcoming = []
    ongoing = []
    finished = []
    for m in matches:
        if m.period_count > 0:
            finished.append(m)
        elif m.datetime_started is not None:
            ongoing.append(m)
        else:
            upcoming.append(m)
    return dict(
        upcoming=sorted(
            upcoming,
            key=lambda m: m.order,
            reverse=False,
        ),
        ongoing=sorted(
            ongoing,
            key=lambda m: m.datetime_started,
            reverse=False,
        ),
        finished=sorted(
            sorted(
                finished,
                key=lambda m: m.datetime_last_period,
                reverse=True,
            ),
            key=lambda m: -float("inf") if m.stage is None else -m.stage.order,
            reverse=False,
        ),
    )


class CourtManager(OrderedModelManager):
    def get_by_natural_key(self, league_slug, name):
        return self.get(
            league__slug=LEAGUE_SLUG.get(league_slug),
            name=name,
        )

class Court(OrderedModel):
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        # Don't edit the league because otherwise existing courts might include
        # matches from different leagues
        editable=False,
    )
    name = models.CharField(
        max_length=50,
        blank=False,
        null=False,
    )

    objects = CourtManager()

    class Meta:
        # The ordering is defined in OrderedModel base class
        ordering = [models.F("order").desc(nulls_first=True)]
        constraints = [
            # FIXME: Because league is non-editable, this constraint cannot be
            # checked in model form validation. So, integrity error is raised if
            # this constraint is broken.
            models.UniqueConstraint(
                fields=["league", "name"],
                name="unique_court_names_in_league",
            ),
        ]

    def natural_key(self):
        return (self.league.slug, self.name)

    natural_key.dependencies = ["leagues.league"]

    def __str__(self):
        return self.name


class MatchManager(OrderedModelManager):

    def get_by_natural_key(self, league_slug, uuid):
        return self.get(
            league__slug=LEAGUE_SLUG.get(league_slug),
            uuid=uuid,
        )

    def with_players(self, players):
        player_qs = Player.objects.filter(
            id__in=[p.id for p in players]
        )
        return self.prefetch_related(
            models.Prefetch(
                "home_team",
                queryset=player_qs,
                to_attr="home_players",
            )
        ).prefetch_related(
            models.Prefetch(
                "away_team",
                queryset=player_qs,
                to_attr="away_players",
            )
        ).filter(
            models.Q(home_team__in=players) & models.Q(away_team__in=players)
        ).distinct()

    def with_period_count(self):
        return annotate_matches_with_period_count(self)

    def with_periods(self):
        return annotate_matches_with_periods(self)

    def with_total_points(self, user, next_up, player=None):
        if next_up is None:
            next_up = Match.objects.none()
        # NOTE: Multiple annotations yield wrong results. So, we need to use a
        # bit more complex solution with subqueries. See:
        # https://stackoverflow.com/a/56619484
        # https://docs.djangoproject.com/en/4.2/topics/db/aggregation/#combining-multiple-aggregations
        total_home_points = self.annotate(
            total_home_points=models.Sum("period__home_points")
        ).filter(pk=models.OuterRef("pk"))
        total_away_points = self.annotate(
            total_away_points=models.Sum("period__away_points")
        ).filter(pk=models.OuterRef("pk"))
        home_ranking_score = self.annotate(
            home_ranking_score=models.Avg("home_team__score")
        ).filter(pk=models.OuterRef("pk"))
        away_ranking_score = self.annotate(
            away_ranking_score=models.Avg("away_team__score")
        ).filter(pk=models.OuterRef("pk"))
        is_home = (
            None if player is None else
            self.filter(
                pk=models.OuterRef("pk"),
                home_team=player,
            ).annotate(
                is_home=models.Count("home_team"),
            )
        )
        is_away = (
            None if player is None else
            self.filter(
                pk=models.OuterRef("pk"),
                away_team=player,
            ).annotate(
                is_away=models.Count("away_team"),
            )
        )
        # datetime_finished = self.filter(
        #     pk=models.OuterRef("pk"),
        # ).annotate(
        #     datetime_finished=models.Max("period__datetime"),
        # )
        matches = (
            self if player is None else
            self.filter(models.Q(home_team=player) | models.Q(away_team=player)).annotate(
                is_home=models.Subquery(
                    is_home.values("is_home"),
                    output_field=models.PositiveIntegerField(),
                ),
                is_away=models.Subquery(
                    is_away.values("is_away"),
                    output_field=models.PositiveIntegerField(),
                ),
            )
        )
        can_start = (
            models.Subquery(
                self.annotate(
                    can_start=models.Case(
                        models.When(
                            pk__in=next_up,
                            then=models.Value(True),
                        ),
                        default=models.Value(False),
                    )
                ).filter(pk=models.OuterRef("pk")).values("can_start"),
                output_field=models.BooleanField(),
            )
        )
        matches_with_user = (
            None if user is None else
            None if user == "admin" else
            models.Subquery(
                Match.objects.filter(
                    models.Q(home_team__uuid=user) |
                    models.Q(away_team__uuid=user)
                ).values("pk")
            )

        )
        can_edit = (
            # If no user, league needs to be not write-protected
            models.Subquery(
                self.annotate(
                    can_edit=models.Case(
                        models.When(
                            league__write_protected=False,
                            then=models.Value(True),
                        ),
                        default=models.Value(False),
                    )
                ).filter(pk=models.OuterRef("pk")).values("can_edit"),
                output_field=models.BooleanField(),
            ) if user is None else
            # Admin can always edit
            models.Value(True) if user == "admin" else
            # Otherwise, either not write-protected or user is in the match
            models.Subquery(
                self.annotate(
                    can_edit=models.Case(
                        models.When(
                            pk__in=matches_with_user,
                            then=models.Value(True),
                        ),
                        default=models.Value(False),
                    )
                ).filter(pk=models.OuterRef("pk")).values("can_edit"),
                output_field=models.BooleanField(),
            )
        )
        return annotate_matches_with_periods(matches).annotate(
            total_home_points=models.Subquery(total_home_points.values("total_home_points"), output_field=models.PositiveIntegerField()),
            total_away_points=models.Subquery(total_away_points.values("total_away_points"), output_field=models.PositiveIntegerField()),
            bonus=models.Case(
                models.When(stage__bonus=None, then=models.F("league__bonus")),
                default=models.F("stage__bonus")
            ),
            points_to_win=models.Case(
                models.When(stage__points_to_win=None, then=models.F("league__points_to_win")),
                default=models.F("stage__points_to_win"),
            ),
            home_ranking_score=models.Subquery(
                home_ranking_score.values("home_ranking_score"),
                output_field=models.FloatField(),
            ),
            away_ranking_score=models.Subquery(
                away_ranking_score.values("away_ranking_score"),
                output_field=models.FloatField(),
            ),
            home_bonus=models.F("bonus") * models.F("home_periods"),
            away_bonus=models.F("bonus") * models.F("away_periods"),
            # datetime_finished=models.Subquery(
            #     datetime_finished.values("datetime_finished"),
            #     output_field=models.DateTimeField(null=True),
            # ),
            datetime_last_period=models.Max("period__datetime"),
            datetime_first_period=models.Min("period__datetime"),
            max_home_points=models.Max("period__home_points"),
            max_away_points=models.Max("period__away_points"),
            can_edit=can_edit,
            can_start=can_start,
        ).distinct().order_by(
            "stage",
            models.F("datetime_last_period").desc(nulls_first=True),
            models.F("datetime_started").desc(nulls_first=True),
            "order",
        )  # Meta.ordering not obeyed, so sort explicitly


class Match(OrderedModel):
    objects = MatchManager()
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        # Don't edit the league because otherwise existing matches might include
        # players from different leagues
        editable=False,
    )
    stage = models.ForeignKey(
        Stage,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        default=None,
    )
    court = models.ForeignKey(
        Court,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        default=None,
    )
    home_team = models.ManyToManyField(
        Player,
        related_name="home_match_set",
        through="HomeTeamPlayer",
    )
    away_team = models.ManyToManyField(
        Player,
        related_name="away_match_set",
        through="AwayTeamPlayer",
    )
    datetime = models.DateTimeField(
        # NOTE: Don't use auto_now_add so the datetime can be edited
        default=timezone.now,
        # Allow forms to ignore this field
        blank=True,
    )
    # Field used to mark a match has been started, so it's ongoing until it gets
    # a result.
    datetime_started = models.DateTimeField(
        blank=True,
        null=True,
        default=None,
    )
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
    )
    last_updated = models.DateTimeField(auto_now=True)

    order_with_respect_to = (
        "league",
    )

    class Meta:
        # The ordering is defined in OrderedModel base class
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["league", "uuid"],
                name="unique_match_uuid_in_league",
            ),
        ]

    def natural_key(self):
        return (self.league.slug, self.uuid)

    natural_key.dependencies = ["leagues.league"]

    def has_result(self):
        return (
            self.total_home_points is not None and
            self.total_away_points is not None and (
                self.total_home_points > 0 or
                self.total_away_points > 0
            )
        )

    def surprisingness(self):
        (p, _) = ranking.scores_to_p_and_q(
            self.home_ranking_score,
            self.away_ranking_score,
        )
        x = self.total_home_points
        y = self.total_away_points
        s = ranking.result_to_surprisingness(x, p, x+y)
        return (s, -s)

    def points_to_win_actual(self):
        s = max(
            0 if self.max_home_points is None else self.max_home_points,
            0 if self.max_home_points is None else self.max_away_points,
        )
        return (
            self.points_to_win if s == 0 else
            min(self.points_to_win, s)
        )

    def expected_points(self):
        return ranking.score_to_result(
            self.home_ranking_score,
            self.away_ranking_score,
            self.points_to_win_actual(),
        )

    def expected_point_ratio(self):
        x = self.home_ranking_score
        y = self.away_ranking_score
        return (
            (1000, 1000 * ranking.score_to_p(y - x)) if x > y else
            (1000 * ranking.score_to_p(x - y), 1000)
        )

    def expected_point_win_percentages(self):
        (p, q) = ranking.scores_to_p_and_q(
            self.home_ranking_score,
            self.away_ranking_score,
        )
        return (100 * p, 100 * q)

    def period_win_probabilities(self):
        return ranking.scores_to_period_probabilities(
            self.home_ranking_score,
            self.away_ranking_score,
            self.points_to_win_actual(),
        )

    @property
    def total_points(self):
        return (
            self.total_home_points,
            self.total_away_points,
        )

    @property
    def periods(self):
        return (
            self.home_periods,
            self.away_periods,
        )

    @property
    def bonus_points(self):
        return (
            self.home_bonus,
            self.away_bonus,
        )

    @property
    def ranking_scores(self):
        return (
            self.home_ranking_score,
            self.away_ranking_score,
        )

    def performance(self):
        if self.total_home_points is None or self.total_away_points is None:
            return (
                (np.nan, np.nan),
                (0, 0, 0, 0),
            )
        p = ranking.result_to_performance(
            self.total_home_points,
            self.total_away_points,
            self.home_ranking_score,
            self.away_ranking_score,
        )
        s = np.log2(p[0]/100) - (np.log2(1-p[0]/100))
        home_stars = np.clip(
            np.floor(s).astype(int),
            0,
            5,
        )
        away_stars = np.clip(
            np.floor(-s).astype(int),
            0,
            5,
        )
        return (
            p,
            (
                home_stars,
                away_stars,
                away_stars,
                home_stars,
            ),
        )

    def clean(self):
        if self.stage is not None and self.stage.league != self.league:
            raise ValidationError(
                "Match league and stage league must be the same"
            )

    def __str__(self):
        return f"{self.uuid} ({self.league.title})"


class HomeTeamPlayer(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    # Don't let players be deleted if they are assigned to a match
    player = models.ForeignKey(Player, on_delete=models.PROTECT)


class AwayTeamPlayer(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    # Don't let players be deleted if they are assigned to a match
    player = models.ForeignKey(Player, on_delete=models.PROTECT)


class Period(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    home_points = models.PositiveIntegerField()
    away_points = models.PositiveIntegerField()
    datetime = models.DateTimeField(
        # NOTE: Don't use auto_now_add so the datetime can be edited
        default=timezone.now,
    )

    @property
    def points(self):
        return (self.home_points, self.away_points)


class RankingScoreManager(models.Manager):

    def with_ranking_stats(self, player):

        count_below = Stage.objects.filter(
            pk=models.OuterRef("stage__pk"),
        ).annotate(
            count_below=models.Count(
                "rankingscore",
                filter=models.Q(
                    rankingscore__score__lt=models.OuterRef("score"),
                )
            )
        ).values("count_below")

        count_above = Stage.objects.filter(
            pk=models.OuterRef("stage__pk"),
        ).annotate(
            count_above=models.Count(
                "rankingscore",
                filter=models.Q(
                    rankingscore__score__gt=models.OuterRef("score"),
                )
            )
        ).values("count_above")

        count_total = Stage.objects.filter(
            pk=models.OuterRef("stage__pk"),
        ).annotate(
            count_total=models.Count(
                "rankingscore",
                filter=models.Q(
                    rankingscore__score__isnull=False,
                )
            )
        ).values("count_total")

        return (
            self
            .filter(
                # Include only stages that contain some matches
                stage__match__isnull=False,
                # Interested only in this player
                player=player,
                # .. and only if it has a ranking in the stage
                score__isnull=False,
            )
            .distinct()
            .annotate(
                count_below=models.Subquery(count_below),
                count_above=models.Subquery(count_above),
                count_total=models.Subquery(count_total),
            )
        )

class RankingScore(models.Model):
    objects = RankingScoreManager()
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    score = models.FloatField(blank=True, null=True, default=None)

    class Meta:
        ordering = ["stage", "-score", "player__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "player"],
                name="unique_players_in_ranking",
            ),
        ]

    @property
    def position(self):
        return 1 + self.count_above

    @property
    def relative_position(self):
        return 100 * (1 - self.count_above / (self.count_total-1))
