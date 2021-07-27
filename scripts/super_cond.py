from ml import ml


def main():

    df = '../original_data/Supercon_data_features_selected.xlsx'
    save = '../analysis'
    target = 'Tc'
    drop_cols = [
                 'name',
                 'group',
                 'ln(Tc)',
                 ]

    ml(df, target, drop_cols, save)


if __name__ == '__main__':
    main()