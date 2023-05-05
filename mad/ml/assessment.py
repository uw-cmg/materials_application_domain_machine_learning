from sklearn.metrics import precision_recall_curve, mean_squared_error
from sklearn.cluster import AgglomerativeClustering
from sklearn.model_selection import RepeatedKFold
from sklearn.model_selection import ShuffleSplit
from sklearn.cluster import estimate_bandwidth
from sklearn.neighbors import KernelDensity
from sklearn.base import clone
from sklearn.svm import SVC

from mad.stats.group import stats, group_metrics
from mad.utils import parallel, find
from mad.ml import splitters
from mad import plots

from sklearn.model_selection import LeaveOneGroupOut
from sklearn import cluster

import pandas as pd
import numpy as np

import copy
import dill
import os


def domain_pred(dist, dist_cut, domain):
    '''
    Predict the domain based on thresholds.
    '''

    do_pred = []
    for i in dist:
        if domain is True:
            if i < dist_cut:
                do_pred.append(True)
            else:
                do_pred.append(False)
        elif domain is False:
            if i >= dist_cut:
                do_pred.append(True)
            else:
                do_pred.append(False)

    return do_pred


def ground_truth(
                 y,
                 y_pred,
                 sigma,
                 ):

    # Define ground truth
    absres = abs(y-y_pred)/sigma

    do_pred = absres < 1
    do_pred = [True if i == 1 else False for i in do_pred]

    return do_pred


def transforms(gs_model, X):

    for step in list(gs_model.best_estimator_.named_steps)[:-1]:

        step = gs_model.best_estimator_.named_steps[step]
        X = step.transform(X)

    return X


def std_pred(gs_model, X_test):

    estimators = gs_model.best_estimator_
    estimators = estimators.named_steps['model']
    estimators = estimators.estimators_

    std = []
    for i in estimators:
        std.append(i.predict(X_test))

    std = np.std(std, axis=0)

    return std


def cv(gs_model, ds_model, X, y, g, train, cv):
    '''
    Do cross validation.
    '''

    g_cv = []
    y_cv = []
    y_cv_pred = []
    y_cv_std = []
    index_cv = []
    dist_cv = []
    sigma_y = []
    for tr, te in cv.split(
                           X[train],
                           y[train],
                           g[train],
                           ):

        gs_model_cv = clone(gs_model)
        ds_model_cv = copy.deepcopy(ds_model)

        gs_model_cv.fit(X[train][tr], y[train][tr])

        X_trans_tr = transforms(
                                gs_model_cv,
                                X[train][tr],
                                )

        X_trans_te = transforms(
                                gs_model_cv,
                                X[train][te],
                                )

        ds_model_cv.fit(X_trans_tr, y[train][tr])

        std = std_pred(gs_model_cv, X_trans_te)

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
        g_cv = np.append(
                         g_cv,
                         g[train][te]
                         )

        index_cv = np.append(index_cv, train[te])
        dist_cv = np.append(
                            dist_cv,
                            ds_model_cv.predict(X_trans_te)
                            )

        sigma_y += [np.std(y[train][tr])]*len(y[train][te])

    data = pd.DataFrame()
    data['g'] = g_cv
    data['y'] = y_cv
    data['y_pred'] = y_cv_pred
    data['y_std'] = y_cv_std
    data['dist'] = dist_cv
    data['index'] = index_cv
    data['split'] = 'cv'
    data['sigma_y'] = sigma_y  # Of the data trained on

    return data


class build_model:

    def __init__(
                 self,
                 gs_model,
                 ds_model,
                 uq_model,
                 splits,
                 ):

        self.gs_model = gs_model
        self.ds_model = ds_model
        self.uq_model = uq_model
        self.splits = splits

    def fit(self, X, y, g):

        # Get some data statistics
        self.ystd = np.std(y)

        # Build the model
        self.gs_model.fit(X, y)

        X_trans = transforms(
                             self.gs_model,
                             X,
                             )
        self.ds_model.fit(X_trans, y)

        # Do cross validation in nested loop
        data_cv = []
        for split in self.splits:
            data_id = cv(
                         self.gs_model,
                         self.ds_model,
                         X,
                         y,
                         g,
                         np.arange(y.shape[0]),
                         split[1],
                         )

            # Define ground truth
            in_domain = ground_truth(
                                     data_id['y'],
                                     data_id['y_pred'],
                                     data_id['sigma_y'],
                                     )

            if 'calibration' == split[0]:

                # Fit on hold out data ID
                self.uq_model.fit(
                                  data_id['y'],
                                  data_id['y_pred'],
                                  data_id['y_std']
                                  )

            data_id['in_domain'] = in_domain
            data_cv.append(data_id)

        data_cv = pd.concat(data_cv)

        # Calibrate uncertainties
        data_cv['y_std'] = self.uq_model.predict(data_cv['y_std'])

        # Z scores
        data_cv['z'] = (data_cv['y']-data_cv['y_pred'])/data_cv['y_std']

        # Normalized uncertaintites
        data_cv['y_std_norm'] = data_cv['y_std']/data_cv['sigma_y']

        self.domain_cut = {'dist': {}, 'y_std_norm': {}}
        for i in [True, False]:

            for j in ['dist', 'y_std_norm']:

                self.domain_cut[j][i] = plots.pr(
                                                 data_cv[j],
                                                 data_cv['in_domain'],
                                                 pos_label=i,
                                                 )

                for key, value in self.domain_cut[j][i].items():
                    thr = self.domain_cut[j][i][key]['Threshold']
                    do_pred = domain_pred(
                                          data_cv[j],
                                          thr,
                                          i,
                                          )

                    if i is True:
                        data_cv['ID by {} for {}'.format(j, key)] = do_pred
                    else:
                        data_cv['OD by {} for {}'.format(j, key)] = do_pred

        # Ground truth for bins
        for i in ['dist', 'y_std_norm']:

            data_cv = plots.intervals(
                                      data_cv,
                                      i,
                                      )

        self.domain_bin = {'dist_bin': {}, 'y_std_norm_bin': {}}
        for i in [True, False]:
            for j in ['dist_bin', 'y_std_norm_bin']:

                self.domain_bin[j][i] = plots.pr(
                                                 data_cv[j],
                                                 data_cv['in_domain_bin'],
                                                 i
                                                 )

                for key, value in self.domain_bin[j][i].items():
                    thr = self.domain_bin[j][i][key]['Threshold']
                    do_pred = domain_pred(
                                          data_cv[j],
                                          thr,
                                          i,
                                          )

                    if i is True:
                        data_cv['ID by {} for {}'.format(j, key)] = do_pred
                    else:
                        data_cv['OD by {} for {}'.format(j, key)] = do_pred

        self.data_cv = data_cv

        return data_cv

    def predict(self, X):

        X_trans = transforms(
                             self.gs_model,
                             X,
                             )

        # Model predictions
        y_pred = self.gs_model.predict(X)
        y_std = std_pred(self.gs_model, X_trans)
        y_std = self.uq_model.predict(y_std)  # Calibrate hold out
        y_std_norm = y_std/self.ystd
        dist = self.ds_model.predict(X_trans)

        pred = {
                'y_pred': y_pred,
                'y_std': y_std,
                'y_std_norm': y_std_norm,
                'dist': dist,
                }

        for i in [True, False]:
            for j in ['dist', 'y_std_norm']:

                for key, value in self.domain_cut[j][i].items():
                    thr = self.domain_cut[j][i][key]['Threshold']
                    do_pred = domain_pred(
                                          pred[j],
                                          thr,
                                          i,
                                          )

                    if i is True:
                        pred['ID by {} for {}'.format(j, key)] = do_pred
                    else:
                        pred['OD by {} for {}'.format(j, key)] = do_pred

        for i in [True, False]:
            for j in ['dist_bin', 'y_std_norm_bin']:

                for key, value in self.domain_bin[j][i].items():
                    thr = self.domain_bin[j][i][key]['Threshold']
                    do_pred = domain_pred(
                                          pred[j.replace('_bin', '')],
                                          thr,
                                          i,
                                          )

                    if i is True:
                        pred['ID by {} for {}'.format(j, key)] = do_pred
                    else:
                        pred['OD by {} for {}'.format(j, key)] = do_pred

        pred = pd.DataFrame(pred)

        return pred


class combine:

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

    def __init__(
                 self,
                 X,
                 y,
                 g=None,
                 gs_model=None,
                 uq_model=None,
                 ds_model=None,
                 insplits=None,
                 splitter=RepeatedKFold(),
                 sub_test=0.0,
                 save='.',
                 ):

        self.X = X  # Features
        self.y = y  # Target
        self.splitter = splitter  # Splitter
        self.insplits = insplits  # Inner splitters
        self.sub_test = sub_test

        # Models
        self.gs_model = gs_model  # Regression
        self.uq_model = uq_model  # UQ
        self.ds_model = ds_model  # Distance

        # Save location
        self.save = save

        # Grouping
        if g is None:
            self.g = np.array(['no-groups']*self.X.shape[0])
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

            # Include some random test points.
            if self.sub_test > 0.0:
                sub = ShuffleSplit(n_splits=1, test_size=self.sub_test)
                sub = sub.split(X[train], y[train], g[train])
                sub = list(sub)[0]

                train = np.array(train)
                test = np.array(test)

                test = np.concatenate([test, train[sub[1]]])
                train = train[sub[0]]

            count += 1
            yield (train, test, count)

    def fit(self, split):

        gs_model = self.gs_model
        uq_model = self.uq_model
        ds_model = self.ds_model
        insplits = self.insplits
        save = self.save

        train, test, count = split  # train/test

        # Fit models
        model = build_model(gs_model, ds_model, uq_model, insplits)
        data_cv = model.fit(self.X[train], self.y[train], self.g[train])
        data_test = model.predict(self.X[test])

        in_domain_test = ground_truth(
                                      self.y[test],
                                      data_test['y_pred'],
                                      model.ystd,
                                      )

        z = (self.y[test]-data_test['y_pred'])/data_test['y_std']

        data_test['y'] = self.y[test]
        data_test['z'] = z
        data_test['g'] = self.g[test]
        data_test['sigma_y'] = model.ystd
        data_test['index'] = test
        data_test['fold'] = count
        data_test['split'] = 'test'
        data_test['in_domain'] = in_domain_test

        data_cv['fold'] = count

        data = pd.concat([data_cv, data_test])
        data['index'] = data['index'].astype(int)

        return data

    def plot(self, df, mets, save):

        i, df = df

        if isinstance(i, tuple):
            mets = mets[(mets['split'] == i[0]) & (mets['fold'] == i[1])]
            i = list(i)
        else:
            i = [i, 'aggregate']
            mets = mets[(mets['split'] == i[0])]

        # Plot ground truth
        job_name = list(map(str, i))
        job_name = os.path.join(*[save, *job_name])

        # Save locations
        sigma_name = os.path.join(job_name, 'sigma')
        dist_name = os.path.join(job_name, 'dissimilarity')

        plots.ground_truth(
                           df['y'],
                           df['y_pred'],
                           df['y_std'],
                           df['sigma_y'],
                           df['in_domain'],
                           job_name
                           )

        # Precision recall for in domain
        for i in [True, False]:
            if i is True:
                j = 'id'
            else:
                j = 'od'

            plots.pr(
                     df['y_std_norm'],
                     df['in_domain'],
                     i,
                     os.path.join(sigma_name, j),
                     )

            plots.pr(
                     df['dist'],
                     df['in_domain'],
                     i,
                     os.path.join(dist_name, j),
                     )

            plots.pr(
                     df['y_std_norm_bin'],
                     df['in_domain_bin'],
                     i,
                     os.path.join(sigma_name+'_bin', j),
                     )

            plots.pr(
                     df['dist_bin'],
                     df['in_domain_bin'],
                     i,
                     os.path.join(dist_name+'_bin', j),
                     )

        # Plot prediction time
        res = abs(df['y']-df['y_pred'])
        plots.assessment(
                         res,
                         df['sigma_y'],
                         df['y_std_norm'],
                         df['in_domain'],
                         sigma_name,
                         )

        plots.assessment(
                         res,
                         df['sigma_y'],
                         df['dist'],
                         df['in_domain'],
                         dist_name,
                         )

        plots.violin(df['dist'], df['in_domain'], dist_name)
        plots.violin(df['dist'], df['in_domain'], sigma_name)

        # Total
        names = df.columns
        names = [i for i in names if ('ID' in i) or ('OD' in i)]
        for name in names:

            if 'ID' in name:
                pos_label = 'id'
            elif 'OD' in name:
                pos_label = 'od'

            if 'y_std' in name:
                w = sigma_name
            elif 'dist' in name:
                w = dist_name

            if 'bin' in name:
                plots.confusion(
                                df['in_domain'+'_bin'],
                                y_pred=df[name].values,
                                pos_label=pos_label,
                                save=os.path.join(*[w+'_bin', pos_label, name])
                                )
            else:
                plots.confusion(
                                df['in_domain'],
                                y_pred=df[name].values,
                                pos_label=pos_label,
                                save=os.path.join(*[w, pos_label, name])
                                )

        # Plot CDF comparison
        plots.cdf_parity(
                         df['z'],
                         df['in_domain'],
                         save=job_name
                         )

        # Plot the confidence curve
        plots.intervals(
                        df,
                        'dist',
                        save=dist_name+'_bin'
                        )

        plots.intervals(
                        df,
                        'y_std_norm',
                        save=sigma_name+'_bin'
                        )

        # Plot parity
        plots.parity(
                     mets,
                     df['y'].values,
                     df['y_pred'].values,
                     df['in_domain'].values,
                     save=job_name
                     )

        plots.violin(res, df['in_domain'], save=job_name)

    def save_model(self):
        '''
        Build one model on all data.
        '''

        gs_model = self.gs_model
        uq_model = self.uq_model
        ds_model = self.ds_model
        insplits = self.insplits
        save = self.save

        # Build the model
        model = build_model(gs_model, ds_model, uq_model, insplits)
        data_cv = model.fit(self.X, self.y, self.g)
        data_cv['fold'] = 0
        data_cv['split'] = 'cv'
        data_cv['index'] = data_cv['index'].astype(int)

        # Statistics
        print('Assessing CV statistics from data used for fitting')
        mets = group_metrics(data_cv, ['split', 'fold', 'in_domain'])

        # Save location
        original_loc = os.path.join(save, 'model')
        os.makedirs(original_loc, exist_ok=True)

        # Plot assessment
        print('Plotting results for CV splits: {}'.format(save))
        parallel(
                 self.plot,
                 data_cv.groupby(['split', 'fold']),
                 mets=mets,
                 save=original_loc,
                 )

        # Save the model
        dill.dump(model, open(os.path.join(original_loc, 'model.dill'), 'wb'))

        # Data
        pd.DataFrame(self.X).to_csv(os.path.join(
                                                 original_loc,
                                                 'X.csv'
                                                 ), index=False)
        X_trans = transforms(model.gs_model, self.X)
        pd.DataFrame(X_trans).to_csv(os.path.join(
                                                  original_loc,
                                                  'X_transformed.csv'
                                                  ), index=False)
        pd.DataFrame(self.y).to_csv(os.path.join(
                                                 original_loc,
                                                 'y.csv'
                                                 ), index=False)
        pd.DataFrame(self.g).to_csv(os.path.join(
                                                 original_loc,
                                                 'g.csv'
                                                 ), index=False)

        if hasattr(model.ds_model, 'bw'):
            bw = model.ds_model.bw
            np.savetxt(os.path.join(
                                    original_loc,
                                    'bw.csv'
                                    ), [bw], delimiter=',')

        data_cv.to_csv(os.path.join(
                                    original_loc,
                                    'train.csv'
                                    ), index=False)

    def assess(self):

        gs_model = self.gs_model
        uq_model = self.uq_model
        ds_model = self.ds_model
        save = self.save

        print('Assessing splits with ML pipeline: {}'.format(save))
        data = parallel(
                        self.fit,
                        self.splits,
                        )

        data = pd.concat(data)
        for i in ['dist', 'y_std_norm']:
            data = plots.intervals(
                                   data,
                                   i,
                                   )

        # Statistics
        print('Assessing test and CV statistics from data used for fitting')
        mets = group_metrics(data, ['split', 'fold', 'in_domain'])

        # Save locations
        assessment_loc = os.path.join(save, 'assessment')
        os.makedirs(assessment_loc, exist_ok=True)

        # Plot assessment
        print('Plotting results for test and CV splits: {}'.format(save))
        parallel(
                 self.plot,
                 data.groupby(['split', 'fold']),
                 mets=mets,
                 save=assessment_loc,
                 )

        # Save csv
        data.to_csv(os.path.join(
                                 assessment_loc,
                                 'assessment.csv'
                                 ), index=False)

        # Now for aggregate assessment
        mets = group_metrics(data, ['split', 'in_domain'])
        parallel(
                 self.plot,
                 data.groupby('split'),
                 mets=mets,
                 save=assessment_loc,
                 )

    def aggregate(self, parent='.'):
        '''
        If other independend runs were ran, then aggreagate those
        results and make overall statistic.
        '''

        paths = find(parent, 'assessment.csv')

        data = []
        for i in paths:
            run = i.split('/')[1]
            i = pd.read_csv(i)
            i['run'] = run
            data.append(i)

        data = pd.concat(data)

        save = os.path.join(parent, 'aggregate')
        os.makedirs(save, exist_ok=True)
        data.to_csv(os.path.join(save, 'aggregate.csv'))

        mets = group_metrics(data, ['split', 'in_domain'])
        parallel(
                 self.plot,
                 data.groupby('split'),
                 mets=mets,
                 save=save,
                 )
