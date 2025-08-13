import functools
import time
import logging

import numpy
from scipy.optimize import minimize
from scipy.stats import binom

# Would be nice to use jax instead of autograd but unfortunately it doesn't work
# on all machines
import autograd.numpy as np
from autograd.scipy.special import gammaln, logsumexp
from autograd import value_and_grad


def calculate_ranking(X, n_players, regularisation, initial=np.nan):
    """
    Format of X:

    [ ( [HOME_PLAYER_ID], [AWAY_PLAYER_ID], HOME_TEAM_POINTS, AWAY_TEAM_POINTS ) ]

    """

    if n_players == 0:
        return ([], [])

    if len(X) == 0:
        nones = [None] * n_players
        return (nones, nones)

    # Remove matches with zero points
    X = list(filter(lambda x: x[2] > 0 or x[3] > 0, X))

    # Parse points
    k_home = np.array([k for (_, _, k, _) in X])
    k_away = np.array([k for (_, _, _, k) in X])
    jss_home = [np.array(xi[0], dtype=int) for xi in X]
    jss_away = [np.array(xi[1], dtype=int) for xi in X]

    # Form matrices that calculate the average of the relevant ranking scores
    # when used as np.dot(A,ranking_scores)
    n_matches = len(X)
    A_home = np.zeros((n_matches, n_players))
    A_away = np.zeros((n_matches, n_players))
    for i in range(n_matches):
        A_home[i,X[i][0]] = 1 / len(X[i][0])
        A_away[i,X[i][1]] = 1 / len(X[i][1])

    def negloglikelihood(x):
        home_x = np.dot(A_home, x)
        away_x = np.dot(A_away, x)
        logz = np.logaddexp(home_x, away_x)
        logp = home_x - logz
        logq = away_x - logz
        # The "imaginary" player for regularisation purposes has a fixed ranking
        # score 0.
        logz_reg = np.logaddexp(x, 0)
        logp_reg = x - logz_reg
        logq_reg = 0 - logz_reg
        return (
            -np.sum(k_home*logp + k_away*logq)
            # Regularisation: Add an "imaginary" player against whom all players
            # have played 1v1 match with result 1-1, or actually, x-x where x is
            # the given regularisation parameter. Note that it doesn't need to
            # be integer.
            -np.sum(regularisation*logp_reg + regularisation*logq_reg)
        )

    # Construct the initial array
    x0 = np.broadcast_to(initial, (n_players,))
    x0 = np.nan_to_num(x0, nan=0.0)

    logging.info("Calculating rankings..")
    t0 = time.monotonic()
    res = minimize(
        value_and_grad(negloglikelihood),
        x0=x0,
        jac=True,
        method="BFGS",  # default anyway
        options=dict(
            # The optimization becomes surprisingly slow. Have some safety value
            # here so that it won't take way too much time. But perhaps the
            # optimization should be optimized...
            maxiter=50,
        )
    )
    t = time.monotonic() - t0
    logging.info(f"Ranking calculations completed in {t} seconds, nfev={res.nfev}: {res.message}")

    # Logarithmic scale scores. Round the scores to 3 decimals because the
    # calculation has numerical inaccuracy anyway, so we don't want to have a
    # different score for players with theoretically equivalen score.
    scores = list(np.round(10 + 10 * (res.x - numpy.amin(res.x)) / np.log(2), decimals=3))
    # Linear scale scores
    #return 10 * np.exp(res.x - numpy.amin(res.x))

    # If a player hasn't played at all, put score to None
    played_ids = functools.reduce(
        lambda acc, ids: acc.union(ids),
        jss_home + jss_away,
        set(),
    )

    not_played_ids = set(range(n_players)).difference(played_ids)

    for i in not_played_ids:
        scores[i] = None

    return (scores, res.x)


def score_to_logp(x):
    return x / 10 * np.log(2)


def score_to_p(x):
    return 2 ** (x / 10)


def scores_to_p(x, y):
    logp = score_to_logp(x)
    logq = score_to_logp(y)
    logz = np.logaddexp(logp, logq)
    return np.exp(logp - logz)


def scores_to_p_and_q(x, y):
    logp = score_to_logp(x)
    logq = score_to_logp(y)
    logz = np.logaddexp(logp, logq)
    return (
        np.exp(logp - logz),
        np.exp(logq - logz),
    )


def score_to_result(x, y, n):
    return (
        (n, n * score_to_p(y - x)) if x >= y else
        (n * score_to_p(x - y), n)
    )


def scores_to_period_probabilities(x, y, n):
    (p, q) = scores_to_p_and_q(x, y)
    # The opponent doesn't reach n points
    r = 100*binom.cdf(n-1, 2*n-1, q)
    return (r, 100-r)


def result_to_performance(
        home_points,
        away_points,
        home_ranking_score,
        away_ranking_score,
):
    n = home_points + away_points
    p = scores_to_p(home_ranking_score, away_ranking_score)
    P0 = 0 if home_points == 0 else binom.cdf(home_points - 1, n, p)
    P1 = binom.cdf(home_points, n, p)
    P = 100 * (P0 + P1) / 2
    return (P, 100-P)


def result_to_surprisingness(x, p, n):
    logP0 = -np.inf if x == 0 else binom.logcdf(x-1, n, p)
    logP1 = binom.logcdf(x, n, p)
    # Average of the two CDF values.
    logP = np.logaddexp(logP0, logP1) - np.log(2)
    # Switch to bits
    log2P = logP / np.log(2)
    # Return log-odds
    return log2P - np.log2(1 - 2**log2P)
