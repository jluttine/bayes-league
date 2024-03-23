import uuid
import secrets

from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from ordered_model.models import OrderedModel


def create_key():
    return secrets.token_urlsafe(30)


class League(models.Model):
    slug = models.SlugField(max_length=30, unique=True)
    title = models.CharField(max_length=100)
    bonus = models.PositiveIntegerField(default=0)
    regularisation = models.FloatField(
        default=0,
        validators=[MinValueValidator(0)]
    )
    write_protected = models.BooleanField(default=False)
    write_key = models.CharField(
        null=True,
        blank=True,
        default=None,
        max_length=50,
        unique=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
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

    def clean(self):
        # Create a key when write-protection is enabled
        if self.write_key is None and self.write_protected:
            self.write_key = create_key()

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
    included = models.ManyToManyField(
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
        ordering = [models.F("order").desc(nulls_first=True)]
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
            models.Q(stage__in=self.included.all())
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


class RankingScore(models.Model):
    stage = models.ForeignKey(Stage, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    score = models.FloatField(blank=True, null=True, default=None)

    class Meta:
        ordering = ["-score", "player__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "player"],
                name="unique_players_in_ranking",
            ),
        ]
