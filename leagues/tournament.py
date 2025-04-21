"""Tools for generating matches"""

from itertools import cycle, chain, repeat, islice

import math
import numpy as np

def arglexmin(criteria):
    criteria = np.asarray(criteria)
    n = np.shape(criteria)[-1]
    return min(
        range(n),
        key=lambda i: tuple(criteria[:,i]),
    )


def exact(n, m, courts=None):
    """n players in total, m players in a team

    .. note::

        A solution perhaps exists only if courts is 1.

    This traverses the entire tree to find a "perfect" solution, so can be fast
    or very slow or might not find a solution

    Assume that there are k courts where k is the maximum number of courts that
    can be utilised (e.g., floor(n/(2*m))).

    Generate rounds until at least one player has played with everyone.

    """

    assert n >= 2*m

    max_k = math.floor(n / (2*m))
    k = (
        max_k if courts is None else
        min(max_k, courts)
    )

    match_count = math.floor(n*(n-1)/(2*m))
    rounds = math.ceil(match_count / k)

    def create_round(matches):

        if np.shape(matches)[0] >= k * rounds:
            # Yey, we're done, we found a complete solution!
            return matches

        # Number of positions that we need to fill with players:
        #
        # no. players in a team * no. teams in a match * no. matches
        position_count = 2 * m * k

        # Filling orders
        game_iter = np.fromiter(
            cycle(
                chain(
                    range(k),
                    reversed(range(k)),
                    range(k),
                    reversed(range(k)),
                ),
            ),
            dtype=int,
            count=position_count,
        )
        side_iter = np.fromiter(
            cycle(
                chain(
                    repeat(1, k),
                    repeat(-1, k),
                    repeat(-1, k),
                    repeat(1, k),
                ),
            ),
            dtype=int,
            count=position_count,
        )

        (together, against) = analyse_teaming(matches)
        # Total number of matches a player has played
        together_diag = np.diag(together)
        # Number of matches played together with other than themselves
        np.fill_diagonal(together.copy(), 0)

        def put_player(new_matches, ind):

            if ind >= position_count:
                # All player positions in this round filled, continue to next
                # round
                return create_round(
                    np.append(matches, new_matches, axis=0),
                )

            game = game_iter[ind]
            side = side_iter[ind]

            criteria = [
                # 4) Has played the least against the players in the other team
                #np.amax(against[:,new_matches[game]==-side], axis=-1, initial=0),
                np.sum(against[:,new_matches[game]==-side], axis=-1, initial=0),
                # 3) Has played the least with the other players in the team
                np.amax(together[:,new_matches[game]==side], axis=-1, initial=0),
                # 2) Has played the least before
                together_diag,
                # 1) Hasn't played on this round yet
                np.sum(np.abs(new_matches), axis=0),
            ]

            player_inds = np.lexsort(criteria)

            for p in player_inds:
                if (criteria[3][p] > 0):
                    # No solution on this path, give up early
                    # print("no solution on this path")
                    return None

                if (
                        #(criteria[0][p] >= m) or
                        (criteria[1][p] >= m-1)
                ):
                    continue

                # Recursively fill the remaining player positions
                tmp = new_matches.copy()
                tmp[game, p] = side
                retval = put_player(tmp, ind+1)

                if retval is not None:
                    # Solution found!
                    return retval

                # Keep on searching..
                continue

            return None

        return put_player(
            np.zeros((k, n), dtype=int),
            0,
        )

    matches = create_round(
        np.empty((0, n), dtype=int)
    )

    if matches is None:
        print("no solution found!")
        return np.empty((0, n), dtype=int)

    return sort_players(sort_rounds(matches, k))


def greedy(n, m, courts=None, special_player_mode=False):
    """n players in total, m players in a team

    This algorithm is greedy, very fast, but not guaranteed to find the best
    solution.

    Generate rounds until at least one player has played with everyone.

    """

    # Not enough players for the teams, so no matches will be created
    if n < 2*m:
        return np.empty((0, n))

    # Number of courts used. Can't utilize more courts than what the number of
    # players allows.
    max_k = math.floor(n / (2*m))
    k = (
        max_k if courts is None else
        min(max_k, courts)
    )

    matches = np.empty((0, n), dtype=int)
    (together, against) = analyse_teaming(matches)
    together0 = together.copy()
    np.fill_diagonal(together0, 0)

    def create_round():
        # Number of positions that we need to fill with players:
        #
        # no. players in a team * no. teams in a match * no. matches
        position_count = 2 * m * k

        # Filling orders
        game_iter = np.fromiter(
            cycle(
                chain(
                    range(k),
                    reversed(range(k)),
                    range(k),
                    reversed(range(k)),
                ),
            ),
            dtype=int,
            count=position_count,
        )
        side_iter = np.fromiter(
            cycle(
                chain(
                    repeat(1, k),
                    repeat(-1, k),
                    repeat(-1, k),
                    repeat(1, k),
                ),
            ),
            dtype=int,
            count=position_count,
        )

        new_matches = np.zeros((k, n), dtype=int)

        position_scores_together = np.zeros((position_count, n))
        position_scores_against = np.zeros((position_count, n))

        for ind in range(position_count):
            game = game_iter[ind]
            side = side_iter[ind]
            player = arglexmin(
                [
                    # Hasn't played on this round yet
                    np.sum(np.abs(new_matches), axis=0),
                    # Has played the least before
                    np.diag(together),
                    # Has played the least with the other players in the team
                    np.sum(together[:,new_matches[game]==side], axis=-1),
                    # Has played the least against the players in the other team
                    np.sum(against[:,new_matches[game]==-side], axis=-1),
                    # The remaining open positions would be bad for the player
                    -np.sum(position_scores_together[(ind+1):,:], axis=0),
                    -np.sum(position_scores_against[(ind+1):,:], axis=0),
                    *list(-np.sort(
                        position_scores_together[(ind+1):,:] +
                        position_scores_against[(ind+1):,:],
                        axis=0,
                    )),
                ]
            )
            position_scores_together += np.where(
                (game == game_iter[:,None]) & (side == side_iter[:,None]),
                together[:,player],
                0,
            )
            position_scores_against += np.where(
                (game == game_iter[:,None]) & (side != side_iter[:,None]),
                against[:,player],
                0,
            )
            new_matches[game, player] = side
        return new_matches

    while (
            # Form matches until everyone has played with everyone enough times
            # or someone has played too often with someone
            (np.amin(together) < m-1) and
            (np.amax(together0) < m)
    ) or (
        # But at least one player should play with everyone enough times
        np.amax(np.amin(together, axis=0)) < m-1
    ):
        matches = np.append(
            matches,
            create_round(),
            axis=0,
        )
        (together, against) = analyse_teaming(matches)
        together0 = together.copy()
        np.fill_diagonal(together0, 0)

    return sort_players(sort_rounds(matches, k))


def analyse_teaming(matches):
    """Calculate how many times each player has played with and against others"""

    home = np.maximum(0, matches)
    away = np.maximum(0, -matches)

    def count(x, y):
        return np.einsum("ki,kj->ij", x, y)

    # Played on the same team
    together = count(home, home) + count(away, away)

    # Played on different teams
    against = count(home, away) + count(away, home)

    return (together, against)


def analyse_breaks(matches, courts):
    """Calculate for each round whether players played or not"""
    n = np.shape(matches)[0]
    groups = np.split(
        np.abs(matches),
        range(courts, n, courts),
    )
    return np.array([np.sum(group, axis=0) for group in groups])


def sort_players(matches):
    """Sort players in matches so that first players have "better" schedules"""

    (together, against) = analyse_teaming(matches)
    # Sort the players
    inds = np.lexsort(
        [
            # 4) Hasn't played excessively against anyone
            np.amax(against, axis=0),
            # 3) Has played "evenly" against everyone
            -np.amin(against, axis=0),
            # 2) Hasn't played "extra" games
            np.amax(together, axis=0),
            # 1) Has played "evenly" with everyone
            -np.amin(together, axis=0),
        ]
    )

    return matches[:,inds]


def group_to_rounds(matches, courts):
    """Reorder matches so that each court has different players in each round

    .. note::

        It seems that it's often impossible to reorder the matches to satisfy
        that condition if it wasn't taken into account at match construction
        time

    """

    if courts != 2:
        raise NotImplementedError("No support for courts!=2 yet")

    matches = np.abs(matches)

    same_players = np.einsum("ik,jk->ij", matches, matches)

    def run(ms, sps):

        n = np.shape(ms)[0]

        if n == 0:
            return ms

        i = 0

        for j in range(1, n):
            if sps[i,j] == 0:
                retval = run(
                    np.delete(ms, (i, j), axis=0),
                    np.delete(
                        np.delete(sps, (i, j), axis=0),
                        (i, j),
                        axis=1,
                    ),
                )
                if retval is not None:
                    return np.append(
                        ms[(i,j),:],
                        retval,
                        axis=0,
                    )

        return None

    retval = run(matches, same_players)

    if retval is None:
        print("No such ordering exists")

    return retval


def sort_rounds(matches, courts):
    """Order match rounds so that breaks are spread evenly"""

    rounds = analyse_breaks(matches, courts)

    r = np.shape(rounds)[0]

    # Initialise result index arrays
    remaining_inds = np.arange(r, dtype=int)
    sorted_inds = np.arange(0, dtype=int)

    for i in range(r):

        # The most breaks still left
        breaks_left = np.sum(rounds[remaining_inds] == 0, axis=0)
        total_breaks_left = np.sum(
            (rounds[remaining_inds] == 0) * breaks_left,
            axis=-1,
        )

        # Count how many "consecutive matches without breaks" streaks per player
        # we're cut by giving breaks to players
        last_round_played = np.amax(
            (rounds[sorted_inds] == 0) * np.arange(1, i+1)[:,None],
            axis=0,
            initial=0,
        )
        matches_since_last_break = i - last_round_played
        total_matches_since_last_break = np.sum(
            (rounds[remaining_inds] == 0) * matches_since_last_break,
            axis=-1,
            initial=0,
        )

        # Count how many "consecutive breaks without matches" streaks per player
        # we're able to cut by assigning players to matches
        last_round_rested = np.amax(
            (rounds[sorted_inds] != 0) * np.arange(1, i+1)[:,None],
            axis=0,
            initial=0,
        )
        breaks_since_last_match = i - last_round_rested
        total_breaks_since_last_match = np.sum(
            (rounds[remaining_inds] != 0) * breaks_since_last_match,
            axis=-1,
        )

        # print("Check")
        # print(rounds[sorted_inds])
        # print("Breaks left")
        # print(breaks_left)
        # print(total_breaks_left)
        # print("Breaks since last match")
        # print(breaks_since_last_match)
        # print(total_breaks_since_last_match)
        # print("Matches since last break")
        # print(matches_since_last_break)
        # print(total_matches_since_last_break)

        j = arglexmin(
            [
                # 1) games to those who have been resting for longest
                -total_breaks_since_last_match,
                # 2) breaks to those who have been playing the longest
                -total_matches_since_last_break,
                # 3) breaks to those who have the most breaks left
                -total_breaks_left,
            ],
        )

        sorted_inds = np.append(sorted_inds, remaining_inds[j])
        remaining_inds = np.delete(remaining_inds, j)

    p = np.shape(matches)[-1]
    return np.reshape(
        np.reshape(matches, (-1, courts, p))[sorted_inds,:,:],
        (-1, p),
    )

