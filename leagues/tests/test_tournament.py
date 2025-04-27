import numpy as np
from numpy import testing
# Don't use Django's test classes because we don't need that stuff here
from unittest import TestCase

from leagues import tournament


class TestTournament(TestCase):

    def test_greedy(self):

        # Make sure a few basic setup work correctly

        # Perfect solution for 4 players with 2-player teams
        (t, a) = tournament.analyse_teaming(tournament.greedy(4, 2))
        testing.assert_array_equal(
            t,
            np.array([
                [3, 1, 1, 1],
                [1, 3, 1, 1],
                [1, 1, 3, 1],
                [1, 1, 1, 3],
            ]),
        )
        testing.assert_array_equal(
            a,
            np.array([
                [0, 2, 2, 2],
                [2, 0, 2, 2],
                [2, 2, 0, 2],
                [2, 2, 2, 0],
            ]),
        )
        # Perfect solution for 5 players with 2-player teams
        (t, a) = tournament.analyse_teaming(tournament.greedy(5, 2))
        testing.assert_array_equal(
            t,
            np.array([
                [4, 1, 1, 1, 1],
                [1, 4, 1, 1, 1],
                [1, 1, 4, 1, 1],
                [1, 1, 1, 4, 1],
                [1, 1, 1, 1, 4],
            ]),
        )
        testing.assert_array_equal(
            a,
            np.array([
                [0, 2, 2, 2, 2],
                [2, 0, 2, 2, 2],
                [2, 2, 0, 2, 2],
                [2, 2, 2, 0, 2],
                [2, 2, 2, 2, 0],
            ]),
        )

        # FIXME: 10 players without special player didn't work, add a test
        #(t, a) = tournament.analyse_teaming(tournament.greedy(10, 2, special_player_mode=False))

        # Decent solution for 10 players with 2-player teams in special-player mode
        (t, a) = tournament.analyse_teaming(tournament.greedy(10, 2, special_player_mode=True))
        # Special player:
        assert t[0,0] == 9  # Plays 9 matches
        testing.assert_equal(t[0,1:], 1)  # Plays with everyone
        testing.assert_equal(a[0,1:], 2)  # Plays against everyone twice
        # Other players:
        testing.assert_equal(np.diag(t)[1:], 7)  # Plays 7 matches
        # FIXME: Plays with everyone at least either against or with
        #testing.assert_array_less(0, a + t)
        np.fill_diagonal(t, 0)
        # Play at most two times with anyone (ideally only once)
        testing.assert_array_less(t, 3)
        # Play with at least 6 different players
        testing.assert_array_less(5, np.sum(t > 0, axis=0))
        # Don't play against anyone more than three times (ideally at most twice)
        testing.assert_array_less(a, 4)
        # Play against at least 7 different players
        testing.assert_array_less(6, np.sum(a > 0, axis=0))

        # Decent solution for 12 players with 2-player teams in special-player mode
        (t, a) = tournament.analyse_teaming(tournament.greedy(12, 2, special_player_mode=True))
        # Special player:
        assert t[0,0] == 11  # Plays 11 matches
        testing.assert_equal(t[0,1:], 1)  # Plays with everyone
        testing.assert_equal(a[0,1:], 2)  # Plays against everyone twice
        # Other players:
        testing.assert_equal(np.diag(t)[1:], 11)  # Plays 11 matches
        # Plays with everyone at least either against or with
        testing.assert_array_less(0, a + t)
        np.fill_diagonal(t, 0)
        # Play at most two times with anyone (ideally only once)
        testing.assert_array_less(t, 3)
        # Play with at least 9 different players
        testing.assert_array_less(8, np.sum(t > 0, axis=0))
        # Don't play against anyone more than four times (ideally at most twice)
        testing.assert_array_less(a, 5)
        # Play against at least 10 different players (ideally all 11)
        testing.assert_array_less(9, np.sum(a > 0, axis=0))
        return
