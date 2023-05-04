import uuid

from django.db import models

class League(models.Model):
    slug = models.SlugField(max_length=30, unique=True)
    title = models.CharField(max_length=100)
    # TODO:
    # - password
    # - public vs unlisted (boolean)


class Player(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    uiid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    class Meta:
        constraints = [
            # In a league, all players have different names
            models.UniqueConstraint(
                fields=["league", "name"],
                name="unique_names_in_league",
            ),
        ]


class Match(models.Model):
    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
    )
    home_team = models.ManyToManyField(
        Player,
        related_name="home_match_set",
    )
    away_team = models.ManyToManyField(
        Player,
        related_name="away_match_set",
    )
    uiid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    class Meta:
        constraints = [
            # I) Each team must have at least one player
            #
            # II) All players must be in the same league
            # models.CheckConstraint(
            #     models.F("league")
            #     name="players_in_same_league",
            # )
            #
            # III) Player can be selected only once and only to either home or
            # away team
        ]


class Ranking(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    players = models.ManyToManyField(Player)
    created_at = models.DateTimeField(auto_now_add=True)
    uiid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)


class RankingScore(models.Model):
    ranking = models.ForeignKey(Ranking, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    score = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ranking", "player"],
                name="unique_players_in_ranking",
            ),
        ]
