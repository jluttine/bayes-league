import uuid

from django.db import models


class League(models.Model):
    slug = models.SlugField(max_length=30, unique=True)
    title = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    # TODO:
    # - password
    # - public / unlisted / private

    def __str__(self):
        return f"{self.slug} - {self.title}"


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
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    uuid = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
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
        return self.annotate(
            period_count=models.Count("period"),
            total_home_points=models.Sum("period__home_points"),
            total_away_points=models.Sum("period__away_points"),
        )


class Match(models.Model):
    objects = MatchManager()
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        # Don't edit the league because otherwise existing matches might include
        # players from different leagues
        editable=False,
    )
    home_team = models.ManyToManyField(
        Player,
        related_name="home_match_set",
    )
    away_team = models.ManyToManyField(
        Player,
        related_name="away_match_set",
    )
    datetime = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(
        unique=True,
        default=uuid.uuid4,
        editable=False,
    )

    class Meta:
        ordering = ["-datetime"]

    def __str__(self):
        return f"{self.uuid}"


class Period(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    home_points = models.PositiveIntegerField()
    away_points = models.PositiveIntegerField()


class Ranking(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    players = models.ManyToManyField(Player, through="RankingScore")
    created_at = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)


class RankingScore(models.Model):
    ranking = models.ForeignKey(Ranking, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    score = models.FloatField()

    class Meta:
        ordering = ["-score"]
        constraints = [
            models.UniqueConstraint(
                fields=["ranking", "player"],
                name="unique_players_in_ranking",
            ),
        ]
