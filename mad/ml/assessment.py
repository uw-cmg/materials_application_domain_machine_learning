from sklearn.metrics import precision_recall_curve
from sklearn.model_selection import RepeatedKFold
from sklearn.base import clone

from mad.stats.group import stats, group_metrics
from mad.utils import parallel
from mad import plots

import statsmodels.api as sm
import pandas as pd
import numpy as np

import copy
import dill
import os


def ground_truth(y, y_pred, y_std, percentile=1, prefit=None):

    # Define ground truth
    absres = abs(y-y_pred)

    # Fit probability density to space
    vals = np.array([y_std, absres]).T

    if prefit is None:
        prefit = sm.nonparametric.KDEMultivariate(vals, var_type='cc')

    pdf = prefit.pdf(vals)

    # Ground truth
    cut = np.percentile(pdf, percentile)

    in_domain_pred = pdf > cut
    in_domain_pred = [True if i == 1 else False for i in in_domain_pred]

    return cut, prefit, in_domain_pred


def transforms(gs_model, X):

    for step in list(gs_model.best_estimator_.named_steps)[:-1]:

        step = gs_model.best_estimator_.named_steps[step]
        X = step.transform(X)

        return X


def std_pred(gs_model, X_test):
    std = []
    estimators = gs_model.best_estimator_
    estimators = estimators.named_steps['model']
    estimators = estimators.estimators_
    X_test = transforms(
                        gs_model,
                        X_test,
                        )
    for i in estimators:
        std.append(i.predict(X_test))

    std = np.std(std, axis=0)
    return std


def cv(gs_model, ds_model, X, y, g, train):
    '''
    Do cross validation.
    '''

    y_cv = []
    y_cv_pred = []
    y_cv_std = []
    index_cv = []
    dist_cv = []
    for tr, te in gs_model.cv.split(
                                    X[train],
                                    y[train],
                                    g[train],
                                    ):

        gs_model_cv = clone(gs_model)
        ds_model_cv = copy.deepcopy(ds_model)

        gs_model_cv.fit(X[train][tr], y[train][tr])
        ds_model_cv.fit(X[train][tr], y[train][tr])

        std = std_pred(gs_model, X[train][te])

        y_cv_pred = np.append(
                              y_cv_pred,
                              gs_model_cv.predict(X[train][te])
                              )

        y_cv_std = np.append(
                             y_cv_std,
                             std
                             )
        y_cv = np.append(
                         y_cv,
                         y[train][te]
                         )

        index_cv = np.append(index_cv, train[te])
        dist_cv = np.append(
                            dist_cv,
                            ds_model_cv.predict(X[train][te])
                            )

    data = pd.DataFrame()
    data['y'] = y_cv
    data['y_pred'] = y_cv_pred
    data['y_std'] = y_cv_std
    data['dist'] = dist_cv
    data['index'] = index_cv
    data['split'] = 'cv'

    return data


class build_model:

    def __init__(self, gs_model, ds_model, uq_model, percentile=1.0):
        self.gs_model = gs_model
        self.ds_model = ds_model
        self.uq_model = uq_model

        self.percentile = percentile

    def fit(self, X, y, g):

        # Build the model
        self.gs_model.fit(X, y)

        X_trans = transforms(
                             self.gs_model,
                             X,
                             )
        self.ds_model.fit(X_trans, y)

        # Do cross validation in nested loop
        data_cv = cv(
                     self.gs_model,
                     self.ds_model,
                     X,
                     y,
                     g,
                     np.arange(y.shape[0])
                     )

        # Fit on hold out data
        self.uq_model.fit(
                          data_cv['y'],
                          data_cv['y_pred'],
                          data_cv['y_std']
                          )

        # Update with calibrated data
        data_cv['y_std'] = self.uq_model.predict(data_cv['y_std'])

        cut, kde, in_domain = ground_truth(
                                           data_cv['y'],
                                           data_cv['y_pred'],
                                           data_cv['y_std'],
                                           self.percentile
                                           )

        self.cut = cut
        self.kde = kde

        score = np.exp(-data_cv['dist'])
        precision, recall, thresholds = precision_recall_curve(
                                                               in_domain,
                                                               score,
                                                               pos_label=True,
                                                               )

        num = 2*recall*precision
        den = recall+precision
        f1_scores = np.divide(
                              num,
                              den,
                              out=np.zeros_like(den), where=(den != 0)
                              )
        max_f1_thresh = thresholds[np.argmax(f1_scores)]

        self.dist_cut = np.log(1/max_f1_thresh)

        in_domain_pred = []
        for i in data_cv['dist']:
            if i< self.dist_cut:
                in_domain_pred.append(True)
            else:
                in_domain_pred.append(False)

        data_cv['in_domain'] = in_domain
        data_cv['in_domain_pred'] = in_domain_pred

        return data_cv

    def predict(self, X):

        X_trans = transforms(
                             self.gs_model,
                             X,
                             )

        # Model predictions
        y_pred = self.gs_model.predict(X)
        y_std = std_pred(self.gs_model, X)
        y_std = self.uq_model.predict(y_std)  # Calibrate hold out
        dist = self.ds_model.predict(X_trans)
        in_domain_pred = [True if i < self.dist_cut else False for i in dist]

        pred = {
                'y_pred': y_pred,
                'y_std': y_std,
                'dist': dist,
                'in_domain_pred': in_domain_pred
                }
        pred = pd.DataFrame(pred)

        return pred


class NestedCV:

    '''
    A class to split data into multiple levels.

    Parameters
    ----------

    X : numpy array
        The original features to be split.

    y : numpy array
        The original target features to be split.

    g : list or numpy array, default = None
        The groups of data to be split.
    '''

    def __init__(self, X, y, g=None, splitter=RepeatedKFold()):

        self.X = X  # Features
        self.y = y  # Target
        self.splitter = splitter  # Splitter

        # Grouping
        if g is None:
            self.g = np.ones(self.X.shape[0])
        else:
            self.g = g

        # Generate the splits
        splits = self.split(
                            self.X,
                            self.y,
                            self.g,
                            self.splitter
                            )
        self.splits = list(splits)

    def split(self, X, y, g, splitter):

        # Train, test splits
        count = -1
        for split in splitter.split(X, y, g):
            train, test = split
            count += 1
            yield (train, test, count)

    def fit(self, split, gs_model, uq_model, ds_model):

        train, test, count = split  # train/test

        # Fit models
        model = build_model(gs_model, ds_model, uq_model)
        data_cv = model.fit(self.X[train], self.y[train], self.g[train])
        data_test = model.predict(self.X[test])

        _, _, in_domain_test = ground_truth(
                                            self.y[test],
                                            data_test['y_pred'],
                                            data_test['y_std'],
                                            model.percentile,
                                            prefit=model.kde
                                            )

        data_test['y'] = self.y[test]
        data_test['index'] = test
        data_test['fold'] = count
        data_test['split'] = 'test'
        data_test['in_domain'] = in_domain_test

        data_cv['fold'] = count

        data = pd.concat([data_cv, data_test])
        data['index'] = data['index'].astype(int)

        return data

    def save_model(self, gs_model, uq_model, ds_model, save='.'):
        '''
        Build one model on all data.
        '''

        # Build the model
        model = build_model(gs_model, ds_model, uq_model)
        data_cv = model.fit(self.X, self.y, self.g)
        data_cv['fold'] = 0
        data_cv['split'] = 'cv'
        data_cv['index'] = data_cv['index'].astype(int)

        # Statistics
        print('Assessing CV statistics from data used for fitting')
        df_stats = stats(data_cv, ['split', 'index'])
        mets = group_metrics(data_cv, ['split', 'fold'])
        mets = stats(mets, ['split'])

        _, _, in_domain_cv = ground_truth(
                                          data_cv['y'],
                                          data_cv['y_pred'],
                                          data_cv['y_std'],
                                          model.percentile,
                                          prefit=model.kde
                                          )

        data_cv['in_domain'] = in_domain_cv

        # Save location
        original_loc = os.path.join(save, 'model')
        os.makedirs(original_loc, exist_ok=True)

        # Plot ground truth
        plots.ground_truth(
                           data_cv['y'],
                           data_cv['y_pred'],
                           data_cv['y_std'],
                           data_cv['in_domain'],
                           os.path.join(original_loc, 'cv')
                           )

        # Plot prediction time
        plots.assessment(
                         data_cv['y_std'],
                         data_cv['dist'],
                         data_cv['in_domain'],
                         os.path.join(original_loc, 'cv')
                         )

        # Precision recall for in domain
        plots.pr(
                 data_cv['dist'],
                 data_cv['in_domain'],
                 os.path.join(original_loc, 'cv')
                 )

        # Plot CDF comparison
        x = (data_cv['y']-data_cv['y_pred'])/data_cv['y_std']
        plots.cdf_parity(x, save=os.path.join(original_loc, 'cv'))

        # Plot parity
        plots.parity(
                     mets,
                     df_stats['y_mean'].values,
                     df_stats['y_pred_mean'].values,
                     save=os.path.join(original_loc, 'cv')
                     )

        # Save the model
        dill.dump(model, open(os.path.join(original_loc, 'model.dill'), 'wb'))

        # Data
        pd.DataFrame(self.X).to_csv(os.path.join(
                                                 original_loc,
                                                 'X.csv'
                                                 ), index=False)
        pd.DataFrame(self.y).to_csv(os.path.join(
                                                 original_loc,
                                                 'y.csv'
                                                 ), index=False)
        pd.DataFrame(self.g).to_csv(os.path.join(
                                                 original_loc,
                                                 'g.csv'
                                                 ), index=False)

        data_cv.to_csv(os.path.join(
                                    original_loc,
                                    'train.csv'
                                    ), index=False)

    def assess(self, gs_model, uq_model, ds_model, save='.'):

        print('Assessing splits with ML pipeline: {}'.format(save))
        data = parallel(
                        self.fit,
                        self.splits,
                        gs_model=gs_model,
                        uq_model=uq_model,
                        ds_model=ds_model,
                        )

        data = pd.concat(data)
        print(data)

        # Statistics
        print('Assessing CV and test statistics')
        df_stats = stats(
                         data,
                         ['split', 'index'],
                         drop=['in_domain_pred', 'in_domain']
                         )
        mets = group_metrics(data, ['split', 'fold'])
        mets = stats(mets, ['split'])

        # Save locations
        assessment_loc = os.path.join(save, 'assessment')
        os.makedirs(assessment_loc, exist_ok=True)

        # Plot assessment
        for i in ['cv', 'test']:
            subdata = data[data['split'] == i]
            subdf = df_stats[df_stats['split'] == i]
            submets = mets[mets['split'] == i]

            # Plot ground truth
            plots.ground_truth(
                               subdata['y'],
                               subdata['y_pred'],
                               subdata['y_std'],
                               subdata['in_domain'],
                               os.path.join(assessment_loc, '{}'.format(i))
                               )

            # Plot prediction time
            plots.assessment(
                             subdata['y_std'],
                             subdata['dist'],
                             subdata['in_domain'],
                             os.path.join(assessment_loc, '{}'.format(i))
                             )

            # Precision recall for in domain
            plots.pr(
                     subdata['dist'],
                     subdata['in_domain'],
                     os.path.join(assessment_loc, '{}'.format(i))
                     )

            # Plot CDF comparison
            x = (subdata['y']-subdata['y_pred'])/subdata['y_std']
            plots.cdf_parity(
                             x,
                             save=os.path.join(assessment_loc, '{}'.format(i))
                             )

            # Plot parity
            plots.parity(
                         submets,
                         subdf['y_mean'].values,
                         subdf['y_pred_mean'].values,
                         subdf['y_pred_sem'].values,
                         save=os.path.join(assessment_loc, '{}'.format(i))
                         )

        # Save csv
        data.to_csv(os.path.join(
                                 assessment_loc,
                                 'assessment.csv'
                                 ), index=False)
