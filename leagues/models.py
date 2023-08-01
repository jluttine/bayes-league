import uuid

from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from ordered_model.models import OrderedModel


class League(models.Model):
    slug = models.SlugField(max_length=30, unique=True)
    title = models.CharField(max_length=100)
    bonus = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    # TODO:
    # - password
    # - public / unlisted / private

    def __str__(self):
        return f"{self.slug} - {self.title}"


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
    previous = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
    )
    bonus = models.PositiveIntegerField(
        blank=True,
        null=True,
        default=None,
    )

    class Meta:
        # The ordering is defined in OrderedModel base class
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["league", "slug"],
                name="unique_stage_slugs_in_league",
            ),
        ]

    def clean(self):
        self.slug = slugify(self.name)
        return

    def get_matches(self):
        return Match.objects.with_total_points().filter(
            models.Q(stage=self) |
            models.Q(stage__in=self.previous.all())
        )

    def __str__(self):
        return self.name


class Player(models.Model):
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
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    uuid = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
    )
    score = models.FloatField(
        blank=True,
        null=True,
        default=None,
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            # In a league, all players have different names
            models.UniqueConstraint(
                fields=["league", "name"],
                name="unique_names_in_league",
            ),
        ]

    def __str__(self):
        return f"{self.uuid} - {self.name}"


class MatchManager(models.Manager):

    def with_total_points(self):
        # NOTE: Multiple annotations yield wrong results. So, we need to use a
        # bit more complex solution with subqueries. See:
        # https://stackoverflow.com/a/56619484
        # https://docs.djangoproject.com/en/4.2/topics/db/aggregation/#combining-multiple-aggregations
        period_count = self.annotate(
            period_count=models.Count("period", distinct=True),
        ).filter(pk=models.OuterRef("pk"))
        total_home_points = self.annotate(
            total_home_points=models.Sum("period__home_points")
        ).filter(pk=models.OuterRef("pk"))
        total_away_points = self.annotate(
            total_away_points=models.Sum("period__away_points")
        ).filter(pk=models.OuterRef("pk"))
        home_periods = self.filter(
            pk=models.OuterRef("pk"),
            period__home_points__gt=models.F("period__away_points"),
        ).annotate(
            home_periods=models.Count("period", distinct=True),
        )
        away_periods = self.filter(
            pk=models.OuterRef("pk"),
            period__away_points__gt=models.F("period__home_points"),
        ).annotate(
            away_periods=models.Count("period", distinct=True),
        )
        # datetime_finished = self.filter(
        #     pk=models.OuterRef("pk"),
        # ).annotate(
        #     datetime_finished=models.Max("period__datetime"),
        # )
        return self.annotate(
            period_count=models.Subquery(period_count.values("period_count"), output_field=models.PositiveIntegerField()),
            total_home_points=models.Subquery(total_home_points.values("total_home_points"), output_field=models.PositiveIntegerField()),
            total_away_points=models.Subquery(total_away_points.values("total_away_points"), output_field=models.PositiveIntegerField()),
            bonus=models.Case(
                models.When(stage__bonus=None, then=models.F("league__bonus")),
                default=models.F("stage__bonus")
            ),
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
            home_bonus=models.F("bonus") * models.F("home_periods"),
            away_bonus=models.F("bonus") * models.F("away_periods"),
            # datetime_finished=models.Subquery(
            #     datetime_finished.values("datetime_finished"),
            #     output_field=models.DateTimeField(null=True),
            # ),
            datetime_finished=models.Max("period__datetime"),
        ).distinct().order_by(
            "stage",
            models.F("datetime_finished").desc(nulls_first=True),
            "-pk",
        )  # Meta.ordering not obeyed, so sort explicitly


class Match(models.Model):
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
    home_team = models.ManyToManyField(
        Player,
        related_name="home_match_set",
    )
    away_team = models.ManyToManyField(
        Player,
        related_name="away_match_set",
    )
    datetime = models.DateTimeField(
        # NOTE: Don't use auto_now_add so the datetime can be edited
        default=timezone.now,
    )
    uuid = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
    )

    class Meta:
        ordering = ["-datetime"]

    def clean(self):
        if self.stage is not None and self.stage.league != self.league:
            raise ValidationError(
                "Match league and stage league must be the same"
            )

    def __str__(self):
        return f"{self.uuid}"


class Period(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    home_points = models.PositiveIntegerField()
    away_points = models.PositiveIntegerField()
    datetime = models.DateTimeField(
        # NOTE: Don't use auto_now_add so the datetime can be edited
        default=timezone.now,
    )


class RankingScore(models.Model):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    score = models.FloatField(blank=True, null=True, default=None)

    class Meta:
        ordering = ["-score"]
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "player"],
                name="unique_players_in_ranking",
            ),
        ]
