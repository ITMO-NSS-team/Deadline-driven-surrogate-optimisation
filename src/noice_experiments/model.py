import csv
import os
import pickle
import random
from collections import Counter

import numpy as np
from scipy.interpolate import interpn

from src.noice_experiments.noisy_wind_files import (
    files_by_stations,
    forecast_files_from_dir,
    extracted_forecast_params
)
from src.utils.files import (
    ForecastFile
)

drf_range = [0.2, 0.4, 0.6000000000000001, 0.8, 1.0, 1.2, 1.4, 1.5999999999999999, 1.7999999999999998,
             1.9999999999999998, 2.1999999999999997, 2.4, 2.6, 2.8000000000000003]

cfw_range = [0.005, 0.01, 0.015, 0.02, 0.025, 0.030000000000000002, 0.035, 0.04, 0.045, 0.049999999999999996]
stpm_range = [0.001, 0.0025, 0.004, 0.0055, 0.006999999999999999, 0.008499999999999999, 0.009999999999999998]


class SWANParams:

    @staticmethod
    def new_instance():
        return SWANParams(drf=random.choice(drf_range), cfw=random.choice(cfw_range), stpm=random.choice(stpm_range))

    def __init__(self, drf, cfw, stpm):
        self.drf = drf
        self.cfw = cfw
        self.stpm = stpm

    def update(self, drf, cfw, stpm):
        self.drf = drf
        self.cfw = cfw
        self.stpm = stpm

    def params_list(self):
        return [self.drf, self.cfw, self.stpm]


class FakeModel:
    def __init__(self, grid_file, error, observations, stations_to_out, forecasts_path, noise_run):
        '''
        :param grid_file: Path to grid file
        :param error: Error metrics to evaluate (forecasts - observations)
        :param forecasts_path: Path to directory with forecast files
        :param noise_run: Index of noise case (corresponds to name of forecasts directory)
        '''

        self.grid_file = grid_file
        self.error = error
        self.observations = observations
        self.stations = stations_to_out
        self.forecasts_path = forecasts_path
        self.noise_run = noise_run
        self._init_grids()

    def _init_grids(self):
        self.grid = self._empty_grid()

        files = forecast_files_from_dir(self.forecasts_path)

        stations = files_by_stations(files, noise_run=self.noise_run, stations=[str(st) for st in self.stations])

        files_by_run_idx = dict()

        for station in stations:
            for file in station:
                _, name = os.path.split(file)
                _, _, run_idx = extracted_forecast_params(file_name=name)

                files_by_run_idx[file] = run_idx

        for row in self.grid_file.rows:
            run_idx = row.id
            forecasts_files = sorted([key for key in files_by_run_idx.keys() if files_by_run_idx[key] == run_idx])

            forecasts = []
            for idx, file_name in enumerate(forecasts_files):
                forecasts.append(FakeModel.Forecast(self.stations[idx], ForecastFile(path=file_name)))

            drf_idx, cfw_idx, stpm_idx = self.params_idxs(row.model_params)
            self.grid[drf_idx, cfw_idx, stpm_idx] = forecasts

        # fintess grid for iterpolation

        # empty array
        self.err_grid = np.asarray([[[[s for s in np.arange(len(stations))] for k in np.arange(self.grid.shape[2])] for
                                     j in np.arange(self.grid.shape[1])] for i in np.arange(self.grid.shape[0])],
                                   dtype=np.float32)

        # calc fitness for every point

        grid_file_path = '../grid-saved-rmse.pik'

        if (not os.path.isfile(grid_file_path)):
            for i in range(0, self.grid.shape[0]):
                for j in range(0, self.grid.shape[1]):
                    for k in range(0, self.grid.shape[2]):
                        forecasts = [forecast for forecast in self.grid[i, j, k]]
                        stat_ind = 0
                        for forecast, observation in zip(forecasts, self.observations):
                            self.err_grid[i, j, k, stat_ind] = self.error(forecast, observation)
                            stat_ind = stat_ind + 1

            pickle_out = open(grid_file_path, 'wb')
            pickle.dump(self.err_grid, pickle_out)
            pickle_out.close()
            print("FINTESS GRID SAVED")
        else:
            with open('../grid-saved-rmse.pik', 'rb') as f:
                self.err_grid = pickle.load(f)

    def _empty_grid(self):
        return np.empty((len(self.grid_file.drf_grid),
                         len(self.grid_file.cfw_grid),
                         len(self.grid_file.stpm_grid)),
                        dtype=list)

    def params_idxs(self, params):
        drf_idx = self.grid_file.drf_grid.index(params.drf)
        cfw_idx = self.grid_file.cfw_grid.index(params.cfw)
        stpm_idx = self.grid_file.stpm_grid.index(params.stpm)

        return drf_idx, cfw_idx, stpm_idx

    def closest_params(self, params):
        drf = min(self.grid_file.drf_grid, key=lambda val: abs(val - params.drf))
        cfw = min(self.grid_file.cfw_grid, key=lambda val: abs(val - params.cfw))
        stpm = min(self.grid_file.stpm_grid, key=lambda val: abs(val - params.stpm))

        return drf, cfw, stpm

    def output(self, params):

        points = (
            np.asarray(self.grid_file.drf_grid), np.asarray(self.grid_file.cfw_grid),
            np.asarray(self.grid_file.stpm_grid))

        interp_mesh = np.array(np.meshgrid(params.drf, params.cfw, params.stpm))
        interp_points = np.rollaxis(interp_mesh, 0, 4).reshape((1, 3))

        out = np.zeros(len(self.stations))
        for i in range(0, len(self.stations)):
            int_obs = interpn(np.asarray(points), self.err_grid[:, :, :, i], interp_points, method="linear",
                              bounds_error=False)
            out[i] = int_obs

        return out

    def output_no_int(self, params):
        drf_idx, cfw_idx, stpm_idx = self.params_idxs(params=params)

        forecasts = [forecast for forecast in self.grid[drf_idx, cfw_idx, stpm_idx]]

        out = []
        for forecast, observation in zip(forecasts, self.observations):
            out.append(self.error(forecast, observation))

        return out

    class Forecast:
        def __init__(self, station_idx, forecast_file):
            self.station_idx = station_idx
            self.file = forecast_file

            self.hsig_series = self._station_series()

        def _station_series(self):
            hsig_idx = 1
            return [float(line.split()[hsig_idx]) for line in self.file.time_series()]


class CSVGridFile:
    def __init__(self, path):
        self.path = path
        self._load()

    def _load(self):
        with open(os.path.join(os.path.dirname(__file__), self.path), newline='') as csvfile:
            reader = csv.DictReader(csvfile)

            self.rows = [CSVGridRow(row) for row in reader]

            drf_values = [row.model_params.drf for row in self.rows]
            cfw_values = [row.model_params.cfw for row in self.rows]
            stpm_values = [row.model_params.stpm for row in self.rows]

            self.drf_grid = unique_values(drf_values)
            self.cfw_grid = unique_values(cfw_values)
            self.stpm_grid = unique_values(stpm_values)

            print(self.drf_grid)
            print(self.cfw_grid)
            print(self.stpm_grid)


class CSVGridRow:
    def __init__(self, row):
        self.id = row['ID']
        self.model_params = self._swan_params(row)

    @classmethod
    def _swan_params(cls, csv_row):
        return SWANParams(drf=float(csv_row['DRF']), cfw=float(csv_row['CFW']), stpm=float(csv_row['STPM']))


def unique_values(values):
    cnt = Counter(values)
    return list(cnt.keys())
