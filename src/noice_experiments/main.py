import csv
import datetime
import os
import random
from functools import partial
from itertools import repeat
from multiprocessing import Pool

import numpy as np
from tqdm import tqdm

from src.evolution.spea2 import SPEA2
from src.noice_experiments.errors import (
    error_dtw_all,
    error_rmse_all,
    error_mae_all,
    error_mae_peak,
    error_rmse_peak
)
from src.noice_experiments.evo_operators import (
    calculate_objectives_interp,
    crossover,
    mutation,
    initial_pop_lhs,
    default_initial_pop
)
from src.noice_experiments.model import (
    CSVGridFile,
    FakeModel
)
from src.noice_experiments.model import SWANParams
from src.utils.files import (
    real_obs_from_files,
    wave_watch_results
)
from src.utils.vis import (
    plot_results,
    plot_population_movement
)

ALL_STATIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

np.random.seed(42)
random.seed(42)


def get_rmse_for_all_stations(forecasts, observations):
    # assert len(observations) == len(forecasts) == 3

    time = np.linspace(1, 253, num=len(forecasts[0].hsig_series))

    obs_series = []
    for obs in observations:
        obs_series.append(obs.time_series(from_date="20140814.120000", to_date="20140915.000000")[:len(time)])

    results_for_stations = np.zeros(len(forecasts))
    for idx in range(0, len(forecasts)):
        results_for_stations[idx] = np.sqrt(
            np.mean((np.array(forecasts[idx].hsig_series) - np.array(obs_series[idx])) ** 2))
    return results_for_stations


def optimize_by_real_obs():
    grid = CSVGridFile('../../samples/wind-exp-params-new.csv')
    obs = [obs.time_series(from_date="20140814.120000", to_date="20140915.000000") for obs in real_obs_from_files()]
    fake_model = FakeModel(grid_file=grid, observations=obs, stations_to_out=[1, 2, 3], error=error_dtw_all,
                           forecasts_path='../../../wind-noice-runs/results_fixed/0', noise_run=0)

    history, archive_history = SPEA2(
        params=SPEA2.Params(max_gens=100, pop_size=10, archive_size=5,
                            crossover_rate=0.8, mutation_rate=0.6, mutation_value_rate=[0.1, 0.005, 0.005]),
        init_population=default_initial_pop,
        objectives=partial(calculate_objectives_interp, fake_model),
        crossover=crossover,
        mutation=mutation).solution()

    plot_population_movement(archive_history, grid)
    params = history.last().genotype

    forecasts = []
    for row in grid.rows:
        if set(row.model_params.params_list()) == set(params.params_list()):
            drf_idx, cfw_idx, stpm_idx = fake_model.params_idxs(row.model_params)
            forecasts = fake_model.grid[drf_idx, cfw_idx, stpm_idx]

    observations = real_obs_from_files()
    plot_results(forecasts=forecasts, observations=observations)
    return history


def model_all_stations():
    grid = CSVGridFile('../../samples/wind-exp-params-new.csv')
    ww3_obs = \
        [obs.time_series() for obs in
         wave_watch_results(path_to_results='../../samples/ww-res/', stations=ALL_STATIONS)]

    model = FakeModel(grid_file=grid, observations=ww3_obs, stations_to_out=ALL_STATIONS, error=error_rmse_all,
                      forecasts_path='../../../wind-postproc/out', noise_run=0)

    return model


def default_params_forecasts(model):
    '''
    Our baseline:  forecasts with default SWAN params
    '''

    closest_params = model.closest_params(params=SWANParams(drf=1.0,
                                                            cfw=0.015,
                                                            stpm=0.00302))
    default_params = SWANParams(drf=closest_params[0], cfw=closest_params[1], stpm=closest_params[2])
    drf_idx, cfw_idx, stpm_idx = model.params_idxs(default_params)
    forecasts = model.grid[drf_idx, cfw_idx, stpm_idx]

    return forecasts


def optimize_by_ww3_obs(train_stations, max_gens, pop_size, archive_size, crossover_rate, mutation_rate,
                        mutation_value_rate, iter_ind, plot_figures=True):
    grid = CSVGridFile('../../samples/wind-exp-params-new.csv')

    ww3_obs = \
        [obs.time_series() for obs in
         wave_watch_results(path_to_results='../../samples/ww-res/', stations=train_stations)]

    error = error_rmse_all
    train_model = FakeModel(grid_file=grid, observations=ww3_obs, stations_to_out=train_stations, error=error,
                            forecasts_path='../../../wind-postproc/out', noise_run=0)

    history, archive_history = SPEA2(
        params=SPEA2.Params(max_gens, pop_size=pop_size, archive_size=archive_size,
                            crossover_rate=crossover_rate, mutation_rate=mutation_rate,
                            mutation_value_rate=mutation_value_rate),
        init_population=initial_pop_lhs,
        objectives=partial(calculate_objectives_interp, train_model),
        crossover=crossover,
        mutation=mutation).solution(verbose=True)

    params = history.last().genotype
    save_archive_history(archive_history, f'history-{iter_ind}.csv')

    if plot_figures:
        test_model = model_all_stations()

        closest_hist = test_model.closest_params(params)
        closest_params_set_hist = SWANParams(drf=closest_hist[0], cfw=closest_hist[1], stpm=closest_hist[2])

        forecasts = []
        for row in grid.rows:

            if set(row.model_params.params_list()) == set(closest_params_set_hist.params_list()):
                drf_idx, cfw_idx, stpm_idx = test_model.params_idxs(row.model_params)
                forecasts = test_model.grid[drf_idx, cfw_idx, stpm_idx]
                if grid.rows.index(row) < 100:
                    print("!!!")
                print("index : %d" % grid.rows.index(row))
                break

        plot_results(forecasts=forecasts,
                     observations=wave_watch_results(path_to_results='../../samples/ww-res/', stations=ALL_STATIONS),
                     baseline=default_params_forecasts(test_model))
        plot_population_movement(archive_history, grid)

    return history


def save_archive_history(history, file_name='history.csv'):
    objectives_amount = len(history[0][0].objectives)

    test_model = model_all_stations()

    with open(file_name, 'w', newline='') as csvfile:
        fieldnames = ['idx', 'gen_idx'] + [f'err_{idx + 1}' for idx in range(len(ALL_STATIONS))] \
                     + ['drf', 'stpm', 'cfw']

        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for gen_idx, gen in enumerate(history):
            for ind_idx, ind in enumerate(gen):
                row_to_write = {}
                idx = gen_idx * len(gen) + ind_idx

                row_to_write['idx'] = idx
                row_to_write['gen_idx'] = gen_idx

                metrics = test_model.output(params=ind.genotype)
                for err_idx, err_value in enumerate(metrics):
                    row_to_write[f'err_{err_idx + 1}'] = err_value

                row_to_write['drf'] = ind.genotype.drf
                row_to_write['stpm'] = ind.genotype.stpm
                row_to_write['cfw'] = ind.genotype.cfw

                writer.writerow(row_to_write)


def run_robustness_exp(max_gens, pop_size, archive_size, crossover_rate, mutation_rate, mutation_value_rate, stations,
                       **kwargs):
    # random.seed(datetime.datetime.now())
    # np.random.seed(int(time.time()))

    grid = CSVGridFile('../../samples/wind-exp-params-new.csv')
    ww3_obs = \
        [obs.time_series() for obs in wave_watch_results(path_to_results='../../samples/ww-res/', stations=stations)]

    train_model = FakeModel(grid_file=grid, observations=ww3_obs, stations_to_out=stations, error=error_rmse_all,
                            forecasts_path='../../../wind-postproc/out', noise_run=0)
    test_model = model_all_stations()
    default_forecasts = default_params_forecasts(test_model)

    ref_metrics = get_rmse_for_all_stations(default_forecasts,
                                            wave_watch_results(path_to_results='../../samples/ww-res/',
                                                               stations=ALL_STATIONS))

    history, archive_history = SPEA2(
        params=SPEA2.Params(max_gens=max_gens, pop_size=pop_size, archive_size=archive_size,
                            crossover_rate=crossover_rate, mutation_rate=mutation_rate,
                            mutation_value_rate=mutation_value_rate),
        init_population=initial_pop_lhs,
        objectives=partial(calculate_objectives_interp, train_model),
        crossover=crossover,
        mutation=mutation).solution(verbose=False)

    exptime2 = str(datetime.datetime.now().time()).replace(":", "-")
    save_archive_history(archive_history, f'rob-exp-bl-{exptime2}.csv')

    params = history.last().genotype

    forecasts = []

    if 'save_figures' in kwargs and kwargs['save_figures'] is True:
        closest_hist = test_model.closest_params(params)
        closest_params_set_hist = SWANParams(drf=closest_hist[0], cfw=closest_hist[1], stpm=closest_hist[2])

        for row in grid.rows:
            if set(row.model_params.params_list()) == set(closest_params_set_hist.params_list()):
                drf_idx, cfw_idx, stpm_idx = test_model.params_idxs(row.model_params)
                forecasts = test_model.grid[drf_idx, cfw_idx, stpm_idx]
                break

        plot_results(forecasts=forecasts,
                     observations=wave_watch_results(path_to_results='../../samples/ww-res/',
                                                     stations=ALL_STATIONS),
                     baseline=default_params_forecasts(test_model),
                     save=True, file_path=kwargs['figure_path'])

    return history.last()


objective_manual_old = {'a': 0, 'archive_size_rate': 0.25, 'crossover_rate': 0.7,
                        'max_gens': 15, 'mutation_p1': 0.1, 'mutation_p2': 0.001,
                        'mutation_p3': 0.0001, 'mutation_rate': 0.7, 'pop_size': 20}

objective_manual = {'a': 0, 'archive_size_rate': 0.5, 'crossover_rate': 0.7,
                    'max_gens': 80, 'mutation_p1': 0.05, 'mutation_p2': 0.001,
                    'mutation_p3': 0.0005, 'mutation_rate': 0.7, 'pop_size': 40}

# max_gens = 80, pop_size = 40, archive_size = 20, crossover_rate = 0.7, mutation_rate = 0.7,
#                        mutation_value_rate=[0.05, 0.001, 0.0005]

stations_for_run_set = [[1],
                        [1, 2],
                        [1, 2, 3],
                        [1, 2, 3, 4],
                        [1, 2, 3, 4, 5],
                        [1, 2, 3, 4, 5, 6],
                        [4],
                        [4, 5],
                        [4, 5, 6],
                        [4, 5, 6, 7],
                        [4, 5, 6, 7, 8],
                        [4, 5, 6, 7, 8, 9],
                        [1],
                        [1, 2],
                        [1, 2, 3],
                        [1, 2, 3, 7],
                        [1, 2, 3, 7, 8],
                        [1, 2, 3, 7, 8, 9]]


stations_for_run_set2 = [[1],
                         [1, 2],
                         [5],
                         [5, 6],
                         [5, 6, 7],
                         [1, 2, 3],
                         [1, 2, 3, 8],
                         [4, 5, 6, 7],
                         [9],
                         [8, 9],
                         [2]]


# stations_for_run_set = [[1,2,3,4,5,6]]


def robustness_statistics():
    param_for_run = objective_manual

    exptime = str(datetime.datetime.now().time()).replace(":", "-")
    os.mkdir(f'../../{exptime}')

    iterations = 10
    run_by = 'rmse_all'

    file_name = f'../bl-{run_by}-{iterations}-runs.csv'
    with open(file_name, 'w', newline='') as csvfile:
        fieldnames = ['ID', 'IterId', 'SetId', 'drf', 'cfw', 'stpm',
                      'rmse_all', 'rmse_peak', 'mae_all', 'mae_peak']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()

    models_to_tests = init_models_to_tests()

    cpu_count = 8

    for iteration in range(iterations):
        print(f'### ITERATION : {iteration}')
        results = []
        with Pool(processes=cpu_count) as p:
            runs_total = len(stations_for_run_set)
            fig_paths = [os.path.join('../..', exptime, str(iteration * runs_total + run)) for run in range(runs_total)]
            all_packed_params = []
            runs_range=list(range(0,len(stations_for_run_set)))
            for st_set_id, station, params, fig_path in zip(runs_range,stations_for_run_set, repeat(param_for_run), fig_paths):
                all_packed_params.append([st_set_id,station, params, fig_path])

            with tqdm(total=runs_total) as progress_bar:
                for _, out in tqdm(enumerate(p.imap(robustness_run, all_packed_params))):
                    results.append(out)
                    progress_bar.update()

        for idx, out in enumerate(results):
            st_set_id_from_param, best = out

            with open(file_name, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                row_to_write = {'ID': iteration * runs_total + idx, 'IterId': iteration, 'SetId': st_set_id_from_param,
                                'drf': best.genotype.drf,
                                'cfw': best.genotype.cfw,
                                'stpm': best.genotype.stpm}
                metrics = all_error_metrics(best.genotype, models_to_tests)
                for metric_name in metrics.keys():
                    stations_metrics = metrics[metric_name]
                    stations_to_write = {}
                    for station_idx in range(len(stations_metrics)):
                        key = f'st{station_idx + 1}'
                        stations_to_write.update({key: stations_metrics[station_idx]})
                    row_to_write.update({metric_name: stations_to_write})

                writer.writerow(row_to_write)


def robustness_run(packed_args):
    st_set_id, stations_for_run, param_for_run, figure_path = packed_args
    print(stations_for_run)
    archive_size = round(param_for_run['archive_size_rate'] * param_for_run['pop_size'])
    mutation_value_rate = [param_for_run['mutation_p1'], param_for_run['mutation_p2'],
                           param_for_run['mutation_p3']]
    best = run_robustness_exp(max_gens=param_for_run['max_gens'],
                              pop_size=param_for_run['pop_size'],
                              archive_size=archive_size,
                              crossover_rate=param_for_run['crossover_rate'],
                              mutation_rate=param_for_run['mutation_rate'],
                              mutation_value_rate=mutation_value_rate,
                              stations=stations_for_run,
                              save_figures=False,
                              figure_path=figure_path)

    return st_set_id, best


def init_models_to_tests():
    metrics = {'rmse_all': error_rmse_all,
               'rmse_peak': error_rmse_peak,
               'mae_all': error_mae_all,
               'mae_peak': error_mae_peak}

    grid = CSVGridFile('../../samples/wind-exp-params-new.csv')
    ww3_obs = \
        [obs.time_series() for obs in
         wave_watch_results(path_to_results='../../samples/ww-res/', stations=ALL_STATIONS)]

    models = {}
    for metric_name in metrics.keys():
        model = FakeModel(grid_file=grid, observations=ww3_obs, stations_to_out=ALL_STATIONS,
                          error=metrics[metric_name],
                          forecasts_path='../../../wind-postproc/out', noise_run=0)
        models[metric_name] = model

    return models


def all_error_metrics(params, models_to_tests):
    metrics = {'rmse_all': error_rmse_all,
               'rmse_peak': error_rmse_peak,
               'mae_all': error_mae_all,
               'mae_peak': error_mae_peak}

    out = {}

    for metric_name in metrics.keys():
        model = models_to_tests[metric_name]

        out[metric_name] = model.output(params=params)

    return out


def prepare_all_fake_models():
    errors = [error_rmse_all]
    grid = CSVGridFile('../../samples/wind-exp-params-new.csv')
    noises = [0, 1, 2, 15, 16, 17, 25, 26]
    for noise in noises:
        for err in errors:
            for stations in stations_for_run_set:
                print(f'configure model for: noise = {noise}; error = {err}; stations = {stations}')
                ww3_obs = \
                    [obs.time_series() for obs in
                     wave_watch_results(path_to_results='../../samples/ww-res/', stations=stations)]
                model = FakeModel(grid_file=grid, observations=ww3_obs, stations_to_out=stations,
                                  error=err,
                                  forecasts_path=f'../../../wind-postproc/out',
                                  noise_run=noise)


def reference_metrics():
    return all_error_metrics(params=SWANParams(drf=1.0, cfw=0.015, stpm=0.00302),
                             models_to_tests=init_models_to_tests())


if __name__ == '__main__':
    robustness_statistics()
    #for iter_id in range(0,10):
    #    optimize_by_ww3_obs([1], max_gens=80, pop_size=40, archive_size=20, crossover_rate=0.7, mutation_rate=0.7,
    #                        mutation_value_rate=[0.05, 0.001, 0.0005], iter_ind=iter_id, plot_figures=False)

    # for iter_ind in range(0, 30):
    #    optimize_by_ww3_obs([1, 2], max_gens=80, pop_size=40, archive_size=20, crossover_rate=0.7, mutation_rate=0.7,
    #                        mutation_value_rate=[0.05, 0.001, 0.0005], iter_ind=iter_ind, plot_figures=False)

    #print(all_error_metrics(params=SWANParams(drf=1.5997924713924645, cfw=0.030010929248229738, stpm=0.0024975825926832843),
    #                  models_to_tests=init_models_to_tests()))
