from matplotlib import pyplot as pl
from mad.functions import chunck
from sklearn import metrics

import matplotlib.colors as colors
import pandas as pd
import numpy as np
import matplotlib
import json
import os


def make_plots(save, bin_size, xaxis, dist):

    df = os.path.join(save, 'aggregate/data.csv')
    df = pd.read_csv(df)

    std = np.ma.std(df['y'].values)
    df['ares'] = abs(df['y'].values-df['y_pred'].values)
    df = df.sort_values(by=[xaxis, 'ares', dist])

    if (dist == 'pdf') or (dist == 'logpdf'):
        sign = -1.0
        dist_label = 'negative '+dist
    else:
        sign = 1.0
        dist_label = dist

    maxx = []
    maxy = []
    minx = []
    miny = []
    vmin = []
    vmax = []
    xs = []
    ys = []
    cs = []
    ds = []
    zs = []

    rows = []
    for subgroup, subvalues in df.groupby('in_domain'):

        x = subvalues[xaxis].values
        y = subvalues['ares'].values
        c = subvalues[dist].values*sign

        # Table data
        mae = metrics.mean_absolute_error(y, x)
        rmse = metrics.mean_squared_error(y, x)**0.5
        r2 = metrics.r2_score(y, x)

        x = list(chunck(x, bin_size))
        y = list(chunck(y, bin_size))
        c = list(chunck(c, bin_size))

        # Skip values that are empty
        if (not x) or (not y) or (not c):
            continue

        # Mask values
        x = np.ma.masked_invalid(x)
        y = np.ma.masked_invalid(y)
        c = np.ma.masked_invalid(c)

        x = np.array([np.ma.mean(i) for i in x])
        y = np.array([(np.ma.sum(i**2)/len(i))**0.5 for i in y])
        c = np.array([np.ma.mean(i) for i in c])

        # Normalization
        x = x/std
        y = y/std

        z = abs(y-x)

        domain_name = subgroup.upper()
        domain_name = '{}'.format(domain_name)
        rmse = '{:.2E}'.format(rmse)
        mae = '{:.2E}'.format(mae)
        r2 = '{:.2f}'.format(r2)

        rows.append([domain_name, rmse, mae, r2])

        maxx.append(np.ma.max(x))
        maxy.append(np.ma.max(y))
        minx.append(np.ma.min(x))
        miny.append(np.ma.min(y))
        vmin.append(np.ma.min(c))
        vmax.append(np.ma.max(c))
        xs.append(x)
        ys.append(y)
        cs.append(c)
        zs.append(z)
        ds.append(subgroup)

    minx = np.append(minx, 0.0)
    miny = np.append(miny, 0.0)

    vmin = np.ma.min(vmin)
    vmax = np.ma.max(vmax)
    maxx = np.ma.max(maxx)
    maxy = np.ma.max(maxy)
    minx = np.ma.min(minx)
    miny = np.ma.min(miny)

    # For plot data export
    data_cal = {}
    data_err = {}

    err_y_label = r'|RMSE/$\sigma_{y}-\sigma_{m}/\sigma_{y}$|'

    fig, ax = pl.subplots()
    fig_err, ax_err = pl.subplots()
    for x, y, c, z, subgroup in zip(xs, ys, cs, zs, ds):

        if subgroup == 'id':
            marker = '1'
            zorder = 3
        elif subgroup == 'ud':
            marker = 'x'
            zorder = 2
        elif subgroup == 'td':
            marker = '.'
            zorder = 1
        else:
            marker = '*'
            zorder = 0

        domain = subgroup.upper()
        dens = ax.scatter(
                          x,
                          y,
                          c=c,
                          marker=marker,
                          label='Domain: {}'.format(domain),
                          cmap=pl.get_cmap('viridis'),
                          vmin=vmin,
                          vmax=vmax,
                          zorder=zorder
                          )

        ax_err.scatter(
                       c,
                       z,
                       marker=marker,
                       label='Domain: {}'.format(domain),
                       zorder=zorder
                       )

        data_err[domain] = {}
        data_err[domain][dist_label] = c.tolist()
        data_err[domain][err_y_label] = z.tolist()

        data_cal[domain] = {}
        data_cal[domain][r'$\sigma_{m}/\sigma_{y}$'] = x.tolist()
        data_cal[domain][r'RMSE/$\sigma_{y}$'] = y.tolist()

    ax.axline([0, 0], [1, 1], linestyle=':', label='Ideal', color='k')

    ax.set_xlim([minx-0.1*abs(minx), maxx+0.1*abs(maxx)])
    ax.set_ylim([miny-0.1*abs(minx), maxy+0.1*abs(maxx)])

    ax.legend()
    ax.set_xlabel(r'$\sigma_{m}/\sigma_{y}$')
    ax.set_ylabel(r'RMSE/$\sigma_{y}$')

    ax_err.legend()
    ax_err.set_xlabel(dist_label)
    ax_err.set_ylabel(err_y_label)

    cbar = fig.colorbar(dens)
    cbar.set_label(dist_label)

    # Make a table
    cols = [r'Domain', r'RMSE', r'MAE', r'$R^2$']
    table = ax.table(
                     cellText=rows,
                     colLabels=cols,
                     colWidths=[0.15]*3+[0.1],
                     loc='lower right',
                     )

    data_cal['table'] = {}
    data_cal['table']['metrics'] = cols
    data_cal['table']['rows'] = rows

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.25, 1.25)

    fig.tight_layout()
    fig_err.tight_layout()

    name = [
            save,
            'aggregate',
            'plots',
            'total',
            'calibration',
            xaxis+'_vs_'+dist
            ]
    name = map(str, name)
    name = os.path.join(*name)
    os.makedirs(name, exist_ok=True)
    name = os.path.join(name, 'calibration.png')
    fig.savefig(name)

    # Save plot data
    jsonfile = name.replace('png', 'json')
    with open(jsonfile, 'w') as handle:
        json.dump(data_cal, handle)

    name = [
            save,
            'aggregate',
            'plots',
            'total',
            'err_in_err',
            xaxis+'_vs_'+dist
            ]
    name = map(str, name)
    name = os.path.join(*name)
    os.makedirs(name, exist_ok=True)
    name = os.path.join(name, 'err_in_err.png')
    fig_err.savefig(name)

    pl.close('all')

    # Save plot data
    jsonfile = name.replace('png', 'json')
    with open(jsonfile, 'w') as handle:
        json.dump(data_err, handle)
