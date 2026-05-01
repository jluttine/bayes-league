from django.test import TestCase, Client

from leagues.models import League, Match, Player
from leagues import views


class TestCreateEvenMatchRounds(TestCase):

    def setUp(self):
        self.league = League.objects.create(
            slug="test-league",
            title="Test League",
        )
        return

    def create_player(self, name, score):
        return Player.objects.create(league=self.league, name=name, score=score)

    def create_match(self, home, away):
        m = Match.objects.create(league=self.league)
        m.home_team.add(*home)
        m.away_team.add(*away)
        return m

    def test_create_even_match_rounds_1(self):
        """Test that each COURT-round contains a player only once.

        Minimal test: 6 players, 2 courts, 2 rounds.
       
          A-B & C-D
          E-F & ???
          ??? & ???
        
        The match at the same time as E-F shouldn't contain E nor F. But we make
        the setup such that without considering the court assignments this would
        happen. Just to test that the scheduling re-orders the matches.

        """

        A = self.create_player("A", 60)
        B = self.create_player("B", 50)
        C = self.create_player("C", 40)
        D = self.create_player("D", 30)
        E = self.create_player("E", 20)
        F = self.create_player("F", 10)

        self.create_match([A], [C])
        self.create_match([A], [D])

        ms = views.create_even_match_rounds(
            [A, B, C, D, E, F],
            n_rounds=2,
            n_courts=2,
        )

        assert ms == [
            # We want to avoid this:
            # 
            #   (A, B), (C, D),
            #   (E, F), (A, E),
            #   (B, C), (D, F),
            # 
            # And, instead, get this (switch A-E and B-C):
            (A, B), (C, D),
            (E, F), (B, C),
            (A, E), (D, F),
        ]

        return

    def test_create_even_match_rounds_2(self):
        """Test that each COURT-round contains a player only once.

        Minimal test: 7 players, 3 courts, 2 rounds.

        """

        A = self.create_player("A", 60)
        B = self.create_player("B", 50)
        C = self.create_player("C", 40)
        D = self.create_player("D", 30)
        E = self.create_player("E", 20)
        F = self.create_player("F", 10)
        G = self.create_player("G", 0)

        self.create_match([A], [C])
        self.create_match([A], [D])
        self.create_match([A], [F])
        self.create_match([A], [G])

        ms = views.create_even_match_rounds(
            [A, B, C, D, E, F, G],
            n_rounds=2,
            n_courts=3,
        )

        assert ms == [
            # We want to avoid this:
            # 
            #   (F, G), (A, B), (C, D),
            #   (E, G), (A, E), (B, C),
            #   (D, F),
            # 
            # And, instead, get this (delay A-E):
            (F, G), (A, B), (C, D),
            (E, G), (B, C), (D, F),
            (A, E),
        ]

        return

