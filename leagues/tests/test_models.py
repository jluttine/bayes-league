from django.test import TestCase, Client

from leagues.models import League, Match, Player


class SimpleTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.league = League.objects.create(
            slug="test-league",
            title="Test League",
        )

    def test_view_league(self):
        response = self.client.get("/league/test-league/")
        self.assertEqual(response.status_code, 200)
        return

    def test_create_player(self):
        response = self.client.post("/league/test-league/players/add/")
        self.assertEqual(response.status_code, 200)
        #response = self.client.get("/league/test-league/players/view/")
        return


class MatchTest(TestCase):

    def setUp(self):
        self.league = League.objects.create(
            slug="test-league",
            title="Test League",
            write_protected=True,
            write_key="foo",
            player_selection_key="bar",
        )
        self.alice = Player.objects.create(
            league=self.league,
            name="Alice",
        )
        self.bob = Player.objects.create(
            league=self.league,
            name="Bob",
        )
        self.carol = Player.objects.create(
            league=self.league,
            name="Carol",
        )
        self.dave = Player.objects.create(
            league=self.league,
            name="Dave",
        )
        self.eve = Player.objects.create(
            league=self.league,
            name="Eve",
        )
        return

    def test_can_edit(self):
        teams = [
            [[self.alice], [self.bob]],
            [[self.alice, self.bob], [self.carol, self.dave]],
            [[self.alice], [self.carol]],
            [[self.alice, self.carol], [self.bob, self.eve]],
        ]

        ms = []
        for (home, away) in teams:
            m = Match.objects.create(league=self.league)
            m.home_team.add(*home)
            m.away_team.add(*away)
            ms.append(m)

        for p in [self.alice, self.bob, self.carol, self.dave, self.eve]:
            self.assertQuerySetEqual(
                Match.objects.with_total_points(p.uuid, None).filter(can_edit=True),
                (Match.objects.filter(home_team=p) | Match.objects.filter(away_team=p)).distinct(),
            )

        return
