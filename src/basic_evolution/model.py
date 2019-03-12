import csv
import os
import pickle
import random
from collections import Counter

import numpy as np
from scipy.interpolate import interpn

from src.basic_evolution.noisy_wind_files import (
    files_by_stations,
    forecast_files_from_dir,
    extracted_forecast_params
)
from src.utils.files import (
    ForecastFile,
    extracted_fidelity,
    presented_fidelity
)

drf_range = [0.2, 0.4, 0.6000000000000001, 0.8, 1.0, 1.2, 1.4, 1.5999999999999999, 1.7999999999999998,
             1.9999999999999998, 2.1999999999999997, 2.4, 2.6, 2.8000000000000003]

cfw_range = [0.005, 0.01, 0.015, 0.02, 0.025, 0.030000000000000002, 0.035, 0.04, 0.045, 0.049999999999999996]
stpm_range = [0.001, 0.0025, 0.004, 0.0055, 0.006999999999999999, 0.008499999999999999, 0.009999999999999998]

GRID_PATH = '../../grid'


class SWANParams:

    @staticmethod
    def new_instance():
        return SWANParams(drf=random.choice(drf_range), cfw=random.choice(cfw_range), stpm=random.choice(stpm_range))

    def __init__(self, drf, cfw, stpm, fidelity=240):
        self.drf = drf
        self.cfw = cfw
        self.stpm = stpm
        self.fidelity = fidelity

    def update(self, drf, cfw, stpm, fidelity):
        self.drf = drf
        self.cfw = cfw
        self.stpm = stpm
        self.fidelity = fidelity

    def params_list(self):
        return [self.drf, self.cfw, self.stpm, self.fidelity]


class AbstractFakeModel:
    def __init__(self, **kwargs):
        pass

    def output(self, params):
        raise NotImplementedError()


class FidelityFakeModel(AbstractFakeModel):
    def __init__(self, grid_file, error, observations, stations_to_out, forecasts_path, noise_run=0):
        '''
        :param grid_file: Path to grid file
        :param error: Error metrics to evaluate (forecasts - observations)
        :param observations: List of time series that correspond to observations
        :param stations_to_out: Stations of interest
        :param forecasts_path: Path to directory with forecast files
        :param fidelity: Index of fidelity case (corresponds to name of forecasts directory)
        :param noise_run: Value of the noise applied to input forcing , by default = 0 (see forecast files naming)
        '''

        super().__init__()

        self.grid_file = grid_file
        self.error = error
        self.observations = observations
        self.stations = stations_to_out
        self.forecasts_path = forecasts_path
        self.noise_run = noise_run

        self._fid_grid = sorted(presented_fidelity(forecast_files_from_dir(self.forecasts_path)))
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

            files_by_fidelity = self._files_by_fidelity(forecasts_files)

            for fidelity in files_by_fidelity:
                files = files_by_fidelity[fidelity]
                forecasts = []
                for idx, file_name in enumerate(files):
                    forecasts.append(FidelityFakeModel.Forecast(self.stations[idx], ForecastFile(path=file_name)))

                drf_idx, cfw_idx, stpm_idx, fid_idx = self.params_idxs(params=SWANParams(drf=row.model_params.drf,
                                                                                         cfw=row.model_params.cfw,
                                                                                         stpm=row.model_params.stpm,
                                                                                         fidelity=fidelity))
                self.grid[drf_idx, cfw_idx, stpm_idx, fid_idx] = forecasts

        # empty array
        self.err_grid = np.zeros(shape=self.grid.shape + (len(stations),))

        # calc fitness for every point
        st_set_id = ("-".join(str(self.stations)))
        file_path = f'grid-saved-{self.error.__name__}_{self.noise_run}_st{st_set_id}.pik'

        grid_file_path = os.path.join(GRID_PATH, file_path)

        if not os.path.isfile(grid_file_path):
            grid_idxs = self.__grid_idxs()

            for i, j, k, m in grid_idxs:
                forecasts = [forecast for forecast in self.grid[i, j, k, m]]
                for forecast, observation in zip(forecasts, self.observations):
                    station_idx = forecasts.index(forecast)
                    self.err_grid[i, j, k, m, station_idx] = self.error(forecast, observation)

            pickle_out = open(grid_file_path, 'wb')
            pickle.dump(self.err_grid, pickle_out)
            pickle_out.close()
            print(f"FITNESS GRID SAVED, file_name: {grid_file_path}")
        else:
            with open(grid_file_path, 'rb') as f:
                self.err_grid = pickle.load(f)

    def __grid_idxs(self):
        idxs = []
        for i in range(self.grid.shape[0]):
            for j in range(self.grid.shape[1]):
                for k in range(self.grid.shape[2]):
                    for m in range(self.grid.shape[3]):
                        idxs.append([i, j, k, m])
        return idxs

    def _errors_at_point(self, packed_values):
        forecasts, observations = packed_values

        errors = []
        for forecast, observation in zip(forecasts, observations):
            errors.append(self.error(forecast, observation))
        return errors

    def _empty_grid(self):

        return np.empty((len(self.grid_file.drf_grid),
                         len(self.grid_file.cfw_grid),
                         len(self.grid_file.stpm_grid),
                         len(self._fid_grid)),
                        dtype=list)

    def _files_by_fidelity(self, files):
        groups = dict()
        for file in files:
            fidelity = extracted_fidelity(file)

            if fidelity not in groups:
                groups[fidelity] = [file]
            else:
                groups[fidelity].append(file)

        return groups

    def params_idxs(self, params):
        drf_idx = self.grid_file.drf_grid.index(params.drf)
        cfw_idx = self.grid_file.cfw_grid.index(params.cfw)
        stpm_idx = self.grid_file.stpm_grid.index(params.stpm)
        fid_idx = self._fid_grid.index(params.fidelity)

        return drf_idx, cfw_idx, stpm_idx, fid_idx

    def closest_params(self, params):
        drf = min(self.grid_file.drf_grid, key=lambda val: abs(val - params.drf))
        cfw = min(self.grid_file.cfw_grid, key=lambda val: abs(val - params.cfw))
        stpm = min(self.grid_file.stpm_grid, key=lambda val: abs(val - params.stpm))
        fid = min(self._fid_grid, key=lambda val: abs(val - params.fidelity))

        return drf, cfw, stpm, fid

    def output(self, params):

        points = (
            np.asarray(self.grid_file.drf_grid), np.asarray(self.grid_file.cfw_grid),
            np.asarray(self.grid_file.stpm_grid),
            np.asarray(self._fid_grid))

        params_fixed = self._fixed_params(params)

        interp_mesh = np.array(
            np.meshgrid(params_fixed.drf, params_fixed.cfw, params_fixed.stpm, params_fixed.fidelity))
        interp_points = abs(np.rollaxis(interp_mesh, 0, 4).reshape((1, 4)))

        out = np.zeros(len(self.stations))
        for i in range(0, len(self.stations)):
            int_obs = interpn(np.asarray(points), self.err_grid[:, :, :, :, i], interp_points, method="linear",
                              bounds_error=False)
            out[i] = int_obs

        return out

    def _fixed_params(self, params):
        params_fixed = SWANParams(drf=min(max(params.drf, min(self.grid_file.drf_grid)), max(self.grid_file.drf_grid)),
                                  cfw=min(max(params.cfw, min(self.grid_file.cfw_grid)), max(self.grid_file.cfw_grid)),
                                  stpm=min(max(params.stpm, min(self.grid_file.stpm_grid)),
                                           max(self.grid_file.stpm_grid)),
                                  fidelity=params.fidelity)
        return params_fixed

    def output_no_int(self, params):
        drf_idx, cfw_idx, stpm_idx, fid_idx = self.params_idxs(params=params)

        forecasts = [forecast for forecast in self.grid[drf_idx, cfw_idx, stpm_idx, fid_idx]]

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
            return [float(line.split(',')[hsig_idx]) for line in self.file.time_series()]


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
