import numpy
from scipy.optimize import minimize

# Would be nice to use jax instead of autograd but unfortunately it doesn't work
# on all machines
import autograd.numpy as np
from autograd.scipy.special import gammaln, logsumexp
from autograd import grad


def calculate_ranking(X, n_players):
    # Parse points
    k_home = np.array([k for (_, _, k, _) in X])
    k_away = np.array([k for (_, _, _, k) in X])
    jss_home = [np.array(xi[0], dtype=int) for xi in X]
    jss_away = [np.array(xi[1], dtype=int) for xi in X]

    def negloglikelihood(x):
        home_x = np.array([
            # Logarithmic scale adding
            #np.sum(np.take(x, js))
            # Linear scale adding
            logsumexp(x[js])
            #logsumexp(np.take(x, js))
            for js in jss_home
        ])
        away_x = np.array([
            # Logarithmic scale adding
            #np.sum(np.take(x, js))
            # Linear scale adding
            logsumexp(x[js])
            #logsumexp(np.take(x, js))
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

    # Logarithmic scale scores
    #return 10 + 10 * (res.x - numpy.amin(res.x)) / np.log(2)
    # Linear scale scores
    return 10 * np.exp(res.x - numpy.amin(res.x))
