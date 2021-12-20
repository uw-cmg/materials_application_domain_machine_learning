from pathos.multiprocessing import ProcessingPool as Pool
from scipy.optimize import minimize
from functools import partial
from tqdm import tqdm

import numpy as np
import sys
import os


def parallel(func, x, *args, **kwargs):
    '''
    Run some function in parallel.
    '''

    pool = Pool(os.cpu_count())
    part_func = partial(func, *args, **kwargs)
    with Pool(os.cpu_count()) as pool:
        data = list(tqdm(
                         pool.imap(part_func, x),
                         total=len(x),
                         file=sys.stdout
                         ))

    return data


def llh(std, res, x):
    '''
    Compute the log likelihood.
    '''

    # Polynomial given coefficients
    def poly(c, std):
        total = 0.0
        for i in range(len(c)):
            total += c[i]*std**i
        return total

    total = np.log(2*np.pi)
    total += np.log(abs(poly(x, std))**2)
    total += (res**2)/(abs(poly(x, std))**2)
    total *= -0.5

    return total


def set_llh(std, y, y_pred, x):
    '''
    Compute the log likelihood for a dataset.
    '''

    res = y-y_pred

    # Get negative to use minimization instead of maximization of llh
    opt = minimize(
                   lambda x: -sum(llh(std, res, x))/len(res),
                   x,
                   method='nelder-mead',
                   )

    params = opt.x

    return params
