from sklearn.cluster import AgglomerativeClustering
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import RepeatedKFold
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from mad.models.space import distance_model
from mad.models.combine import domain_model
from mad.models.uq import ensemble_model
from mad.ml.assessment import nested_cv
from mad.datasets import load_data
from mad.ml import splitters


def main():

    run_name = 'run'

    # Load data
    data = load_data.diffusion()
    X = data['data']
    y = data['target']
    g = data['class_name']
    n_repeats = 1

    # ML Distance model
    ds_model = distance_model(dist='kde')

    # ML UQ function
    uq_model = ensemble_model(params=[0.0, 1.0])

    # ML Pipeline
    scale = StandardScaler()
    model = RandomForestRegressor()

    grid = {}
    grid['model__n_estimators'] = [100]
    pipe = Pipeline(steps=[
                           ('scaler', scale),
                           ('model', model),
                           ])
    gs_model = GridSearchCV(pipe, grid, cv=RepeatedKFold(n_repeats=1))

    # Types of sampling to test
    splits = [('calibration', RepeatedKFold(n_repeats=n_repeats))]

    for i in [2, 3]:

        # Cluster Splits
        top_split = splitters.BootstrappedClusterSplit(
                                                       AgglomerativeClustering,
                                                       n_repeats=n_repeats,
                                                       n_clusters=i
                                                       )

        splits.append(('agglo_{}'.format(i), top_split))

    # Fit models
    model = domain_model(gs_model, ds_model, uq_model, splits, save='test')
    #data_test = nested_cv(X, y, g, model, splits).run()
    data_test = model.fit(X, y, g)

    print(data_test)


if __name__ == '__main__':
    main()
