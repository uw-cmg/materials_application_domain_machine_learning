from sklearn.ensemble import RandomForestRegressor
from sklearn import cluster

from sklearn.model_selection import RepeatedKFold
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from mad.ml import splitters, feature_selectors, domain
from mad.datasets import load_data, statistics
from mad.plots import parity, calibration

import numpy as np


def main():
    '''
    Test ml workflow
    '''

    seed = 14987
    save = 'run_supercond'
    points = None
    sampling = None

    # Load data
    data = load_data.super_cond()
    df = data['frame']
    X = data['data']
    y = data['target']
    d = data['class_name']

    # Splitters
    top_split = splitters.BootstrappedLeaveOneGroupOut(5, d)
    mid_split = RepeatedKFold(5, 5)
    bot_split = RepeatedKFold(5, 1)

    # ML setup
    scale = StandardScaler()
    selector = feature_selectors.no_selection()

    # Random forest regression
    grid = {}
    model = RandomForestRegressor()
    grid['model__n_estimators'] = [100, 200, 500, 1000]
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
                            save
                            )

    splits.assess_domain()  # Do ML
    splits.aggregate()  # combine all of the ml data
    statistics.folds(save)  # Gather statistics from data
    parity.make_plots(save)  # Make parity plots
    calibration.make_plots(save, 1000)


if __name__ == '__main__':
    main()
