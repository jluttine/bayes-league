import functools

import numpy
from scipy.optimize import minimize

# Would be nice to use jax instead of autograd but unfortunately it doesn't work
# on all machines
import autograd.numpy as np
from autograd.scipy.special import gammaln, logsumexp
from autograd import grad


def team_scores(x, jss):
    return np.array([
        # Geometric mean, that is, arithmetic mean on logarithmic scale
        np.mean(x[js])
        # Product, that is, sum on logarithmic scale. Geometric mean is better.
        #np.sum(x[js])
        # Adding
        #logsumexp(x[js])
        for js in jss
    ])


def calculate_ranking(X, n_players, regularisation):
    """
    Format of X:

    [ ( [HOME_PLAYER_ID], [AWAY_PLAYER_ID], HOME_TEAM_POINTS, AWAY_TEAM_POINTS ) ]

    """

    if n_players == 0:
        return []

    if len(X) == 0:
        return [None] * n_players

    # Remove matches with zero points
    X = list(filter(lambda x: x[2] > 0 or x[3] > 0, X))

    # Parse points
    k_home = np.array([k for (_, _, k, _) in X])
    k_away = np.array([k for (_, _, _, k) in X])
    jss_home = [np.array(xi[0], dtype=int) for xi in X]
    jss_away = [np.array(xi[1], dtype=int) for xi in X]

    def negloglikelihood(x):
        home_x = team_scores(x, jss_home)
        away_x = team_scores(x, jss_away)
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

    res = minimize(
        negloglikelihood,
        x0=np.zeros(n_players),
        jac=grad(negloglikelihood),
    )

    # Logarithmic scale scores
    scores = list(10 + 10 * (res.x - numpy.amin(res.x)) / np.log(2))
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

    return scores
