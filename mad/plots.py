from sklearn.metrics import (
                             precision_recall_curve,
                             confusion_matrix,
                             ConfusionMatrixDisplay,
                             auc
                             )

from matplotlib import pyplot as pl

import numpy as np

import matplotlib
import json
import os

# Font styles
font = {'font.size': 16, 'lines.markersize': 10}
matplotlib.rcParams.update(font)


def parity(
           mets,
           y,
           y_pred,
           y_pred_sem=None,
           name='',
           units='',
           save='.'
           ):
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

    os.makedirs(save, exist_ok=True)

    m = mets.to_dict(orient='records')[0]
    if y_pred_sem is not None:

        rmse_sigma = m[r'$RMSE/\sigma_{y}$_mean']
        rmse_sigma_sem = m[r'$RMSE/\sigma_{y}$_sem']

        rmse = m[r'$RMSE$_mean']
        rmse_sem = m[r'$RMSE$_sem']

        mae = m[r'$MAE$_mean']
        mae_sem = m[r'$MAE$_sem']

        r2 = m[r'$R^{2}$_mean']
        r2_sem = m[r'$R^{2}$_sem']

        label = r'$RMSE/\sigma=$'
        label += r'{:.2} $\pm$ {:.2}'.format(
                                             rmse_sigma,
                                             rmse_sigma_sem
                                             )
        label += '\n'
        label += r'$RMSE=$'
        label += r'{:.2} $\pm$ {:.2}'.format(rmse, rmse_sem)
        label += '\n'
        label += r'$MAE=$'
        label += r'{:.2} $\pm$ {:.2}'.format(mae, mae_sem)
        label += '\n'
        label += r'$R^{2}=$'
        label += r'{:.2} $\pm$ {:.2}'.format(r2, r2_sem)

    else:

        rmse_sigma = m[r'$RMSE/\sigma$']
        rmse = m[r'$RMSE$']
        mae = m[r'$MAE$']
        r2 = m[r'$R^{2}$']

        label = r'$RMSE/\sigma_{y}=$'
        label += r'{:.2}'.format(rmse_sigma)
        label += '\n'
        label += r'$RMSE=$'
        label += r'{:.2}'.format(rmse)
        label += '\n'
        label += r'$MAE=$'
        label += r'{:.2}'.format(mae)
        label += '\n'
        label += r'$R^{2}=$'
        label += r'{:.2}'.format(r2)

    fig, ax = pl.subplots()

    if y_pred_sem is not None:
        ax.errorbar(
                    y,
                    y_pred,
                    yerr=y_pred_sem,
                    linestyle='none',
                    marker='.',
                    markerfacecolor='None',
                    zorder=1,
                    color='b',
                    )
    ax.scatter(
               y,
               y_pred,
               marker='.',
               zorder=2,
               color='b',
               label=label,
               )

    limits = []
    min_range = min(min(y), min(y_pred))
    max_range = max(max(y), max(y_pred))
    span = max_range-min_range
    limits.append(min_range-0.1*span)
    limits.append(max_range+0.1*span)

    # Line of best fit
    ax.plot(
            limits,
            limits,
            label=r'$y=\hat{y}$',
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

    h = 8
    w = 8

    fig.set_size_inches(h, w, forward=True)
    fig.savefig(os.path.join(save, 'parity.png'))
    pl.close(fig)

    # Repare plot data for saving
    data = {}
    data['y_pred_id'] = list(y_pred)
    data['y_id'] = list(y)
    data['metrics'] = m

    if y_pred_sem is not None:
        data['y_pred_sem'] = list(y_pred_sem)

    jsonfile = os.path.join(save, 'parity.json')
    with open(jsonfile, 'w') as handle:
        json.dump(data, handle)


def cdf(x):
    '''
    Plot the quantile quantile plot for cummulative distributions.
    inputs:
        x = The residuals normalized by the calibrated uncertainties.
    '''

    nx = len(x)
    nz = 100000
    z = np.random.normal(0, 1, nz)  # Standard normal distribution

    # Need sorting
    x = sorted(x)
    z = sorted(z)

    # Cummulative fractions
    xfrac = np.arange(nx)/(nx-1)
    zfrac = np.arange(nz)/(nz-1)

    # Interpolation to compare cdf
    eval_points = sorted(list(set(x+z)))
    y_pred = np.interp(eval_points, x, xfrac)  # Predicted
    y = np.interp(eval_points, z, zfrac)  # Standard Normal

    # Area bertween ideal Gaussian and observed
    area = np.trapz(abs(y_pred-y), x=y, dx=0.00001)

    return y, y_pred, area


def cdf_parity(x, in_domain, save):
    '''
    Plot the quantile quantile plot for cummulative distributions.
    inputs:
        x = The residuals normalized by the calibrated uncertainties.
    '''

    os.makedirs(save, exist_ok=True)

    out_domain = ~in_domain

    data = {}
    fig, ax = pl.subplots()

    y, y_pred, area = cdf(x)
    ax.plot(
            y,
            y_pred,
            zorder=0,
            color='b',
            label='Total Area: {:.3f}'.format(area),
            )
    data['y'] = list(y)
    data['y_pred'] = list(y_pred)

    if x[in_domain].shape[0] > 1:
        y_id, y_pred_id, in_area = cdf(x[in_domain])
        ax.plot(
                y_id,
                y_pred_id,
                zorder=0,
                color='g',
                label='ID Area: {:.3f}'.format(in_area),
                )
        data['y_id'] = list(y_id)
        data['y_pred_id'] = list(y_pred_id)

    if x[out_domain].shape[0] > 1:
        y_od, y_pred_od, out_area = cdf(x[out_domain])
        ax.plot(
                y_od,
                y_pred_od,
                zorder=0,
                color='r',
                label='OD Area: {:.3f}'.format(out_area),
                )
        data['y_od'] = list(y_od)
        data['y_pred_od'] = list(y_pred_od)

    # Line of best fit
    ax.plot(
            [0, 1],
            [0, 1],
            color='k',
            linestyle=':',
            zorder=1,
            )

    ax.legend()
    ax.set_ylabel('Predicted CDF')
    ax.set_xlabel('Standard Normal CDF')

    h = 8
    w = 8

    fig.set_size_inches(h, w, forward=True)
    ax.set_aspect('equal')
    fig.savefig(os.path.join(save, 'cdf_parity.png'))

    pl.close(fig)

    jsonfile = os.path.join(save, 'cdf_parity.json')
    with open(jsonfile, 'w') as handle:
        json.dump(data, handle)


def ground_truth(y, y_pred, y_std, in_domain, save):

    os.makedirs(save, exist_ok=True)

    std = np.std(y)
    absres = abs(y-y_pred)/std
    y_std = y_std/std

    out_domain = ~in_domain

    fig, ax = pl.subplots()

    ax.scatter(absres[in_domain], y_std[in_domain], color='g', marker='.')
    ax.scatter(absres[out_domain], y_std[out_domain], color='r', marker='x')

    ax.set_xlabel(r'$|y-\hat{y}|/\sigma_{y}$')
    ax.set_ylabel(r'$\sigma_{c}/\sigma_{y}$')

    fig.savefig(os.path.join(save, 'ground_truth.png'))
    pl.close(fig)

    # Repare plot data for saving
    data = {}
    data['x_green'] = list(absres[in_domain])
    data['y_green'] = list(y_std[in_domain])
    data['x_red'] = list(absres[out_domain])
    data['y_red'] = list(y_std[out_domain])

    jsonfile = os.path.join(save, 'ground_truth.json')
    with open(jsonfile, 'w') as handle:
        json.dump(data, handle)


def assessment(
               y_std,
               std,
               dist,
               in_domain,
               save,
               transform=False,
               thresh=None
               ):

    y_std = y_std/std
    os.makedirs(save, exist_ok=True)

    out_domain = ~in_domain

    if transform == 'gpr_std':
        dist = -np.log10(1e-8+1-dist)
        if thresh:
            thresh = -np.log10(1e-8+1-thresh)

    elif transform == 'kde':
        dist = -np.log10(1e-8-dist)
        if thresh:
            thresh = -np.log10(1e-8-thresh)

    fig, ax = pl.subplots()

    ax.scatter(dist[in_domain], y_std[in_domain], color='g', marker='.')
    ax.scatter(dist[out_domain], y_std[out_domain], color='r', marker='x')

    if thresh:
        ax.axvline(thresh, color='k')

    ax.set_ylabel(r'$\sigma/\sigma_{y}$')

    if transform == 'gpr_std':
        ax.set_xlabel(r'$-log_{10}(1e-8+1-GPR_{\sigma})$')
    elif transform == 'kde':
        ax.set_xlabel(r'$-log_{10}(1e-8-KDE)$')
    else:
        ax.set_xlabel('dist')

    fig.savefig(os.path.join(save, 'assessment.png'))
    pl.close(fig)

    # Repare plot data for saving
    data = {}
    data['x_green'] = list(dist[in_domain])
    data['y_green'] = list(y_std[in_domain])
    data['x_red'] = list(dist[out_domain])
    data['y_red'] = list(y_std[out_domain])

    if thresh:
        data['vertical'] = thresh

    jsonfile = os.path.join(save, 'assessment.json')
    with open(jsonfile, 'w') as handle:
        json.dump(data, handle)


def pr(dist, in_domain, save=False, choice=None):

    baseline = sum(in_domain)/len(in_domain)
    relative_base = 1-baseline  # The amount of area to gain in PR

    score = 1/(1+np.exp(dist))

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

    # Relative f1
    precision_rel = precision-baseline
    num = 2*recall*precision_rel
    den = recall+precision_rel
    f1_rel = np.divide(
                       num,
                       den,
                       out=np.zeros_like(den), where=(den != 0)
                       )

    # Maximum F1 score
    rel_f1_index = np.argmax(f1_rel)
    rel_f1_thresh = thresholds[rel_f1_index]
    rel_f1 = f1_rel[rel_f1_index]
    rel_f1_relative = (rel_f1-baseline)/relative_base

    # Maximum F1 score
    max_f1_index = np.argmax(f1_scores)
    max_f1_thresh = thresholds[max_f1_index]
    max_f1 = f1_scores[max_f1_index]
    max_f1_relative = (max_f1-baseline)/relative_base

    # AUC score
    auc_score = auc(recall, precision)
    auc_relative = (auc_score-baseline)/relative_base

    # Maximize recall while keeping precision equal to highest value
    max_auc_index = np.where(precision == max(precision[:-1]))[0][0]
    max_auc = recall[:-1][max_auc_index]
    max_auc_relative = (max_auc-baseline)/relative_base
    max_auc_thresh = thresholds[max_auc_index]

    # Convert back
    rel_f1_thresh = np.log(1/rel_f1_thresh-1)
    max_f1_thresh = np.log(1/max_f1_thresh-1)
    max_auc_thresh = np.log(1/max_auc_thresh-1)

    if save is not False:

        os.makedirs(save, exist_ok=True)

        fig, ax = pl.subplots()

        ax.plot(
                recall,
                precision,
                color='b',
                label='AUC: {:.2f}'.format(auc_score),
                )
        ax.hlines(
                  baseline,
                  color='r',
                  linestyle=':',
                  label='Baseline: {:.2f}'.format(baseline),
                  xmin=0.0,
                  xmax=1.0,
                  )

        ax.scatter(
                   max_auc,
                   precision[:-1][max_auc_index],
                   marker='o',
                   label='Max Recall: {:.2f}'.format(max_auc),
                   )
        ax.scatter(
                   recall[max_f1_index],
                   precision[max_f1_index],
                   marker='o',
                   label='Max F1: {:.2f}'.format(max_f1),
                   )
        ax.scatter(
                   recall[rel_f1_index],
                   precision[rel_f1_index],
                   marker='o',
                   label='Relative Max F1: {:.2f}'.format(rel_f1),
                   )

        ax.legend()

        ax.set_xlim(0.0, 1.05)
        ax.set_ylim(0.0, 1.05)

        ax.set_xlabel('Recall')
        ax.set_ylabel('Precision')

        fig.savefig(os.path.join(save, 'pr.png'))
        pl.close(fig)

        # Repare plot data for saving
        data = {}
        data['recall'] = list(recall)
        data['precision'] = list(precision)
        data['baseline'] = baseline
        data['auc'] = auc_score
        data['auc_relative'] = auc_relative
        data['max_f1'] = max_f1
        data['max_f1_relative'] = max_f1_relative
        data['max_f1_thresh'] = max_f1_thresh
        data['rel_f1'] = rel_f1
        data['rel_f1_relative'] = rel_f1_relative
        data['rel_f1_thresh'] = rel_f1_thresh
        data['max_auc'] = max_auc
        data['max_auc_relative'] = max_auc_relative
        data['max_auc_thresh'] = max_auc_thresh

        jsonfile = os.path.join(save, 'pr.json')
        with open(jsonfile, 'w') as handle:
            json.dump(data, handle)

    if choice == 'max_auc':
        return max_auc_thresh
    elif choice == 'max_f1':
        return max_f1_thresh
    elif choice == 'rel_f1':
        return rel_f1_thresh


def confusion(y_true, y_pred, save='.'):

    conf = confusion_matrix(y_true, y_pred)

    # In case only one class exists
    if conf.shape == (1, 1):

        t = list(set(y_true))[0]
        p = list(set(y_pred))[0]

        if (t == p) and (t == 0):
            conf = np.array([[conf[0, 0], 0], [0, 0]])
        elif (t == p) and (t == 1):
            conf = np.array([[0, 0], [0, conf[0, 0]]])
        else:
            raise 'You done fucked up'

    fig, ax = pl.subplots()
    disp = ConfusionMatrixDisplay(conf, display_labels=['OD', 'ID'])
    disp.plot(ax=ax)
    fig_data = conf.tolist()

    disp.figure_.savefig(os.path.join(save, 'confusion.png'))
    pl.close(fig)

    jsonfile = os.path.join(save, 'confusion.json')
    with open(jsonfile, 'w') as handle:
        json.dump(fig_data, handle)
