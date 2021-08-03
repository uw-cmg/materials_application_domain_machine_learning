from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn import cluster

from sklearn.model_selection import RepeatedKFold
from sklearn.model_selection import GridSearchCV
from sklearn.gaussian_process.kernels import RBF
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn import metrics

from matplotlib import pyplot as pl
from scipy.spatial.distance import cdist

import pandas as pd
import numpy as np
import random
import json
import os

from functions import parallel


def parity(mets, y, y_pred, y_pred_sem, name, units, save):
    '''
    Make a paroody plot.

    inputs:
        mets = The regression metrics.
        y = The true target value.
        y_pred = The predicted target value.
        y_pred_sem = The standard error of the mean in predicted values.
        name = The name of the target value.
        units = The units of the target value.
        save = The directory to save plot.
    '''

    label = r''
    for i, j, k in zip(
                       mets['metric'],
                       mets['result_mean'],
                       mets['result_sem']
                       ):
        label += r'{}={:.2} $\pm$ {:.1}'.format(i, j, k)
        label += '\n'
    label = label[:-2]  # Compensate for last break

    fig, ax = pl.subplots()
    ax.errorbar(
                y,
                y_pred,
                yerr=y_pred_sem,
                linestyle='none',
                marker='.',
                zorder=0,
                label='Data'
                )

    ax.text(
            0.55,
            0.05,
            label,
            transform=ax.transAxes,
            bbox=dict(facecolor='white', edgecolor='black')
            )

    limits = []
    limits.append(min(min(y), min(y_pred))-0.25)
    limits.append(max(max(y), max(y_pred))+0.25)

    # Line of best fit
    ax.plot(
            limits,
            limits,
            label=r'$45^{\circ}$ Line',
            color='k',
            linestyle=':',
            zorder=1
            )

    ax.set_aspect('equal')
    ax.set_xlim(limits)
    ax.set_ylim(limits)
    ax.legend(loc='upper left')

    ax.set_ylabel('Predicted {} {}'.format(name, units))
    ax.set_xlabel('Actual {} {}'.format(name, units))

    fig.tight_layout()
    fig.savefig(os.path.join(save, '{}_parity.png'.format(name)))
    pl.close(fig)

    # Repare plot data for saving
    data = {}
    data['y_pred'] = list(y_pred)
    data['y_pred_sem'] = list(y_pred_sem)
    data['y'] = list(y)
    data['metrics'] = mets.to_dict()

    jsonfile = os.path.join(save, 'parity.json')
    with open(jsonfile, 'w') as handle:
        json.dump(data, handle)


def eval_metrics(y, y_pred):
    '''
    Evaluate standard prediction metrics.
    '''

    rmse = metrics.mean_squared_error(y, y_pred)**0.5
    rmse_sig = rmse/np.std(y)
    mae = metrics.mean_absolute_error(y, y_pred)
    r2 = metrics.r2_score(y, y_pred)

    results = {
               'result': [rmse, rmse_sig, mae, r2],
               'metric': [r'$RMSE$', r'$RMSE/\sigma$', r'$MAE$', r'$R^{2}$']
               }

    return results


def distance_link(X_train, X_test, dist_type):
    '''
    Get the distances based on a metric.

    inputs:
        X_train = The features of the training set.
        X_test = The features of the test set.
        dist = The distance to consider.

    ouputs:
        dists = A dictionary of distances.
    '''

    # Get the inverse of the covariance matrix from training
    dists = {}
    if dist_type == 'mahalanobis':
        vi = np.linalg.inv(np.cov(X_train.T))
        dist = cdist(X_train, X_test, dist_type, VI=vi)
    else:
        dist = cdist(X_train, X_test, dist_type)

    dists[dist_type+'_mean'] = np.mean(dist, axis=0)
    dists[dist_type+'_max'] = np.max(dist, axis=0)
    dists[dist_type+'_min'] = np.min(dist, axis=0)

    return dists


def distance(X_train, X_test):
    '''
    Determine the distance from set X_test to set X_train.
    '''

    selected = [
                'mahalanobis',
                'euclidean',
                'cityblock',
                ]

    dists = {}
    for i in selected:
        dists.update(distance_link(X_train, X_test, i))

    return dists


def stats(df, cols):
    '''
    Get the statistic of a dataframe.
    '''

    groups = df.groupby(cols)
    mean = groups.mean().add_suffix('_mean')
    sem = groups.sem().add_suffix('_sem')
    count = groups.count().add_suffix('_count')
    df = mean.merge(sem, on=cols)
    df = df.merge(count, on=cols)

    return df


def inner(indx, X, y, pipes):
    '''
    The inner loop from nested cross validation.
    '''

    df = {}
    mets = []

    tr_indx, te_indx = indx
    X_train, X_test = X[tr_indx], X[te_indx]
    y_train, y_test = y[tr_indx], y[te_indx]

    # Save true values
    df['actual'] = y_test
    df['index'] = te_indx

    # Calculate distances from test set cases to traning set
    for key, value in distance(X_train, X_test).items():
        if key in df:
            df[key] += list(value)
        else:
            df[key] = list(value)

    for pipe in pipes:
        pipe.fit(X_train, y_train)
        pipe_best = pipe.best_estimator_

        pipe_best_model = pipe_best.named_steps['model']
        pipe_best_scaler = pipe_best.named_steps['scaler']

        model_type = pipe_best_model.__class__.__name__
        scaler_type = pipe_best_scaler.__class__.__name__

        # If model is random forest regressor
        if model_type == 'RandomForestRegressor':
            y_test_pred = pipe_best.predict(X_test)
            X_trans = pipe_best_scaler.transform(X_test)
            pipe_estimators = pipe_best_model.estimators_
            std = [i.predict(X_trans) for i in pipe_estimators]
            std = np.std(std, axis=0)
            df[model_type+'_std'] = std

        # If model is gaussian process regressor
        elif model_type == 'GaussianProcessRegressor':
            y_test_pred, std = pipe_best.predict(X_test, return_std=True)
            df[model_type+'_std'] = std

        m = pd.DataFrame(eval_metrics(y_test, y_test_pred))
        m['model'] = model_type
        m['scaler'] = scaler_type

        mets.append(m)
        df[model_type+'_pred'] = y_test_pred

    df = pd.DataFrame(df)
    mets = pd.concat(mets)

    return df, mets


def outer(split, pipes, X, y, save):
    '''
    Save the true values, predicted values, distances, and model error.

    inputs:
        split = The splitting method.
        pipes = The machine learning pipeline.
        X = The feature matrix.
        y = The target values.
        save = The directory to save values
    '''

    # Gather split data in parallel
    data = parallel(inner, list(split.split(X)), X=X, y=y, pipes=pipes)

    # Format data correctly
    df = [pd.DataFrame(i[0]) for i in data]
    mets = [pd.DataFrame(i[1]) for i in data]

    # Combine frames
    df = pd.concat(df)
    mets = pd.concat(mets)

    # Get statistics
    dfstats = stats(df, 'index')
    metsstats = stats(mets, ['metric', 'model', 'scaler'])

    # Convert to dataframes
    dfstats = dfstats.reset_index()
    metsstats = metsstats.reset_index()

    # Generate parity plots
    for i in set(metsstats['model']):

        m = metsstats[metsstats['model'].isin([i])]

        parity(
               m,
               dfstats['actual_mean'],
               dfstats[i+'_pred_mean'],
               dfstats[i+'_pred_sem'],
               i,
               '',
               save
               )

    # Save data
    df.to_csv(
              os.path.join(save, 'data.csv'),
              index=False
              )
    dfstats.to_csv(
                   os.path.join(save, 'data_stats.csv'),
                   index=False
                   )
    mets.to_csv(
                os.path.join(save, 'metrics.csv'),
                index=False
                )
    metsstats.to_csv(
                     os.path.join(save, 'metrics_stats.csv'),
                     index=False
                     )


class splitters:
    '''
    A class used to handle splitter types.
    '''

    def repkf(*argv, **kargv):
        '''
        Repeated K-fold cross validation.
        '''

        return RepeatedKFold(*argv, **kargv)

    def repcf(*argv, **kargv):
        '''
        Custom cluster splitter by fraction.
        '''

        return clust_split(*argv, **kargv)


class clust_split:
    '''
    Custom slitting class which pre-clusters data and then splits on a
    fraction.
    '''

    def __init__(self, clust, reps, *args, **kwargs):
        '''
        inputs:
            clust = The class of cluster from Scikit-learn.
            reps = The number of times to apply splitting.
        '''

        self.clust = clust(*args, **kwargs)
        self.reps = reps

    def get_n_splits(self, X=None, y=None, groups=None):
        '''
        A method to return the number of splits.
        '''

        return self.reps

    def split(self, X, y=None, groups=None):
        '''
        Cluster data, randomize cluster order, randomize case order,
        and then split into train and test sets self.reps number of times.

        inputs:
            X = The features.
        outputs:
            A generator for train and test splits.
        '''

        self.clust.fit(X)

        df = pd.DataFrame(X)
        df['cluster'] = self.clust.labels_

        order = list(set(self.clust.labels_))
        n_clusts = len(order)
        split_num = X.shape[0]//n_clusts

        for rep in range(self.reps):

            # Shuffling
            random.shuffle(order)  # Cluster order
            df = df.sample(frac=1)  # Sample order

            test = []
            train = []
            for i in order:

                data = df.loc[df['cluster'] == i]
                for j in data.index:
                    if len(test) < split_num:
                        test.append(j)
                    else:
                        train.append(j)

            yield train, test


def ml(loc, target, drop, save):
    '''
    Define the machine learning workflow with nested cross validation
    for gaussian process regression and random forest.
    '''

    # Output directory creation
    os.makedirs(save, exist_ok=True)

    # Data handling
    if 'xlsx' in loc:
        df = pd.read_excel(loc)
    else:
        df = pd.read_csv(loc)

    df.drop(drop, axis=1, inplace=True)

    X = df.loc[:, df.columns != target].values
    y = df[target].values

    # ML setup
    scale = StandardScaler()
    split = splitters.repcf(cluster.KMeans, 3, n_clusters=10, n_jobs=1)
    split = splitters.repkf(2, 2)

    # Gaussian process regression
    kernel = RBF()
    model = GaussianProcessRegressor()
    grid = {}
    grid['model__alpha'] = [1e-1]  # np.logspace(-2, 2, 5)
    grid['model__kernel'] = [RBF(i) for i in np.logspace(-2, 2, 5)]
    pipe = Pipeline(steps=[('scaler', scale), ('model', model)])
    gpr = GridSearchCV(pipe, grid, cv=split)

    # Random forest regression
    model = RandomForestRegressor()
    grid = {}
    grid['model__n_estimators'] = [100]
    grid['model__max_features'] = [None]
    grid['model__max_depth'] = [None]
    pipe = Pipeline(steps=[('scaler', scale), ('model', model)])
    rf = GridSearchCV(pipe, grid, cv=split)

    # Evaluate each pipeline
    pipes = [gpr, rf]

    # Nested CV
    outer(split, pipes, X, y, save)
