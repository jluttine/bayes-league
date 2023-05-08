import numpy
import jax.numpy as np
from jax.scipy.special import gammaln, logsumexp
from scipy.optimize import minimize
from jax import grad


def calculate_ranking(X, n_players):
    # Parse points
    k_home = np.array([k for (_, _, k, _) in X])
    k_away = np.array([k for (_, _, _, k) in X])
    jss_home = [np.array(xi[0], dtype=int) for xi in X]
    jss_away = [np.array(xi[1], dtype=int) for xi in X]

    def negloglikelihood(x):
        home_x = np.array([
            logsumexp(np.take(x, js))
            for js in jss_home
        ])
        away_x = np.array([
            logsumexp(np.take(x, js))
            for js in jss_away
        ])
        logz = np.logaddexp(home_x, away_x)
        logp = home_x - logz
        logq = away_x - logz
        return -np.sum(k_home*logp + k_away*logq)

    res = minimize(
        negloglikelihood,
        x0=np.zeros(n_players),
        jac=grad(negloglikelihood),
    )

    # Translate minimum ranking to 0 and transform from natural logarithm to log2
    return 1000 + 1000 * (res.x - numpy.amin(res.x)) / numpy.log(2)
