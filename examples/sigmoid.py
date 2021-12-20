from sklearn.ensemble import RandomForestRegressor
from sklearn import cluster

from sklearn.model_selection import RepeatedKFold
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from mad.ml import splitters, feature_selectors, domain, set_class
from mad.datasets import load_data, statistics
from mad.plots import parity, calibration

import numpy as np


def main():
    '''
    Test ml workflow
    '''

    seed = 14987
    save = 'run'
    points = 100
    uq_coeffs_Start = [0.0, 1.1, 0.0]

    # Load data
    data = load_data.sigmoid(3)
    df = data['frame']
    X = data['data']
    y = data['target']
    d = set_class.cluster(X, cluster.KMeans(3))

    # Splitters
    top_split = splitters.BootstrappedLeaveOneGroupOut(10, d)
    mid_split = RepeatedKFold(5, 1)
    bot_split = RepeatedKFold(5, 1)

    # ML setup
    scale = StandardScaler()
    selector = feature_selectors.no_selection()

    # Random forest regression
    grid = {}
    model = RandomForestRegressor()
    grid['model__n_estimators'] = [100]
    grid['model__max_features'] = [None]
    grid['model__max_depth'] = [None]
    pipe = Pipeline(steps=[
                           ('scaler', scale),
                           ('select', selector),
                           ('model', model)
                           ])
    rf = GridSearchCV(pipe, grid, cv=bot_split)

    # Evaluate
    splits = domain.builder(
                            rf,
                            X,
                            y,
                            d,
                            top_split,
                            mid_split,
                            save,
                            seed=seed,
                            uq_coeffs_Start=uq_coeffs_Start
                            )

    splits.assess_domain()  # Do ML
    splits.aggregate()  # combine all of the ml data
    statistics.folds(save)  # Gather statistics from data
    parity.make_plots(save)  # Make parity plots
    calibration.make_plots(save, points, 'std', 'pdf')
    calibration.make_plots(save, points, 'stdcal', 'pdf')


if __name__ == '__main__':
    main()
