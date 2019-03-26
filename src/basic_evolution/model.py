import csv
import os
import pickle
import random
import sys
from collections import Counter
from datetime import datetime

from pyDOE import lhs
from scipy.stats.distributions import norm

import numpy as np
from pyKriging.krige import kriging
from scipy.interpolate import interpn

from src.basic_evolution.noisy_wind_files import (
    files_by_stations,
    forecast_files_from_dir,
    extracted_forecast_params
)
from src.utils.files import (
    ForecastFile,
    extracted_fidelity,
    presented_fidelity,
    observations_from_range
)

drf_range = [0.2, 0.4, 0.6000000000000001, 0.8, 1.0, 1.2, 1.4, 1.5999999999999999, 1.7999999999999998,
             1.9999999999999998, 2.1999999999999997, 2.4, 2.6, 2.8000000000000003]

cfw_range = [0.005, 0.01, 0.015, 0.02, 0.025, 0.030000000000000002, 0.035, 0.04, 0.045, 0.049999999999999996]
stpm_range = [0.001, 0.0025, 0.004, 0.0055, 0.006999999999999999, 0.008499999999999999, 0.009999999999999998]
fid_time_range = [60, 90, 120, 180]
fid_space_range = [14,28,56]


GRID_PATH = '../../grid-new'


class SWANParams:

    @staticmethod
    def new_instance():
        return SWANParams(drf=random.choice(drf_range), cfw=random.choice(cfw_range), stpm=random.choice(stpm_range),fid_time=random.choice(fid_time_range),fid_space=random.choice(fid_space_range))

    def __init__(self, drf, cfw, stpm, fidelity_time, fidelity_space):
        self.drf = drf
        self.cfw = cfw
        self.stpm = stpm
        self.fid_time = fidelity_time
        self.fid_space = fidelity_space

    def update(self, drf, cfw, stpm, fidelity_time, fidelity_space):
        self.drf = drf
        self.cfw = cfw
        self.stpm = stpm
        self.fid_time = fidelity_time
        self.fid_space = fidelity_space

    def params_list(self):
        return [self.drf, self.cfw, self.stpm, self.fid_time, self.fid_space]


class AbstractFakeModel:
    def __init__(self, **kwargs):
        pass

    def output(self, params):
        raise NotImplementedError()


class FidelityFakeModel(AbstractFakeModel):
    def __init__(self, grid_file, error, observations, stations_to_out, forecasts_path, noise_run=0, **kwargs):
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

        if 'forecasts_range' in kwargs:
            self.forecasts_range = kwargs['forecasts_range']
        else:
            self.forecasts_range = (0, 1)

        if 'is_surrogate' in kwargs:
            self.is_surrogate = kwargs['is_surrogate']
        else:
            self.is_surrogate = False

        if 'sur_points' in kwargs:
            self.sur_points = kwargs['sur_points']
        else:
            self.sur_points = 50

        self._init_fidelity_grids()
        self._init_grids()

        if self.is_surrogate:
            self._init_surrogate()

    # TODO: extract class instead of a function
    def _init_surrogate(self):
        X = []
        #for drf in self.grid_file.drf_grid:
        #    for cfw in self.grid_file.cfw_grid:
        #        for stpm in self.grid_file.stpm_grid:
        #            X.append([drf, cfw, stpm])

        #X = np.asarray(X)
        self.k = []

        dim_num=5
        samples_grid = lhs(dim_num, self.sur_points, 'center')

        for idx, params_range in enumerate([drf_range, cfw_range, stpm_range, fid_time_range, fid_space_range]):
            samples_grid[:, idx] = norm(loc=np.mean(params_range), scale=np.std(params_range)).ppf(samples_grid[:, idx])

        points_for_krig = [SWANParams(drf=sample[0], cfw=sample[1], stpm=sample[2], fidelity_time=sample[3], fidelity_space=sample[4]) for sample in samples_grid]
        X_train = [[sample[0],sample[1],sample[2],sample[3],sample[4]] for sample in samples_grid]
        X_train = np.asarray(X_train)

        for i in range(len(self.stations)):
            print(i)
            k6d_train = [self.output_kriging(points_for_krig[k])[0] for k in range(self.sur_points)]
           # k6d_train = np.asarray(k6d_train)

            # Creating kriging from kriging class
            print("kriging start")
            print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

            self.k2 = kriging(X_train, k6d_train, name='multikrieg')
            self.k2.train(optimizer='ga')
            self.k.append(self.k2)
            print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            print("kriging end")

    def _init_fidelity_grids(self):
        fid_time, fid_space = presented_fidelity(forecast_files_from_dir(self.forecasts_path))
        self._fid_time_grid = sorted(fid_time)
        self._fid_space_grid = sorted(fid_space)

    def _init_grids(self):
        self.grid = self._empty_grid()

        files = forecast_files_from_dir(self.forecasts_path)

        if not files: sys.exit("EMPTY FORECAST")

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
                    forecasts.append(FidelityFakeModel.Forecast(self.stations[idx], ForecastFile(path=file_name),
                                                                range_values=self.forecasts_range))

                fid_time, fid_space = fidelity
                drf_idx, cfw_idx, stpm_idx, fid_time_idx, fid_space_idx = self.params_idxs(
                    params=SWANParams(drf=row.model_params.drf,
                                      cfw=row.model_params.cfw,
                                      stpm=row.model_params.stpm,
                                      fidelity_time=fid_time,
                                      fidelity_space=fid_space))

                self.grid[drf_idx, cfw_idx, stpm_idx, fid_time_idx, fid_space_idx] = forecasts

        # empty array
        self.err_grid = np.zeros(shape=self.grid.shape + (len(stations),))

        # calc fitness for every point
        st_set_id = ("-".join(str(self.stations)))
        file_path = f'grid-saved-{self.error.__name__}_range_{self.forecasts_range}_st{st_set_id}.pik'

        grid_file_path = os.path.join(GRID_PATH, file_path)

        if not os.path.isfile(grid_file_path):
            grid_idxs = self.__grid_idxs()

            for i, j, k, m, n in grid_idxs:
                forecasts = [forecast for forecast in self.grid[i, j, k, m, n]]
                for forecast, observation in zip(forecasts, self.observations):
                    station_idx = forecasts.index(forecast)

                    obs_in_range = observations_from_range(observation, self.forecasts_range)
                    self.err_grid[i, j, k, m, n, station_idx] = self.error(forecast, obs_in_range)

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
                        for n in range(self.grid.shape[4]):
                            idxs.append([i, j, k, m, n])
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
                         len(self._fid_time_grid),
                         len(self._fid_space_grid)),
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
        fid_time_idx = self._fid_time_grid.index(params.fid_time)
        fid_space_idx = self._fid_space_grid.index(params.fid_space)

        return drf_idx, cfw_idx, stpm_idx, fid_time_idx, fid_space_idx

    def closest_params(self, params):
        drf = min(self.grid_file.drf_grid, key=lambda val: abs(val - params.drf))
        cfw = min(self.grid_file.cfw_grid, key=lambda val: abs(val - params.cfw))
        stpm = min(self.grid_file.stpm_grid, key=lambda val: abs(val - params.stpm))
        fid_time = min(self._fid_time_grid, key=lambda val: abs(val - params.fid_time))
        fid_space = min(self._fid_space_grid, key=lambda val: abs(val - params.fid_space))

        return drf, cfw, stpm, fid_time, fid_space

    def output_kriging(self, params):

        points = (
            np.asarray(self.grid_file.drf_grid), np.asarray(self.grid_file.cfw_grid),
            np.asarray(self.grid_file.stpm_grid),
            np.asarray(self._fid_time_grid),
            np.asarray(self._fid_space_grid))

        params_fixed = self._fixed_params(params)

        interp_mesh = np.array(
            np.meshgrid(params_fixed.drf, params_fixed.cfw, params_fixed.stpm, params_fixed.fid_time, params.fid_space))
        interp_points = abs(np.rollaxis(interp_mesh, 0, 6).reshape((1, 5)))

        out = np.zeros(len(self.stations))
        for i in range(0, len(self.stations)):
            int_obs = interpn(np.asarray(points), self.err_grid[:, :, :, :, :, i], interp_points, method="linear",
                              bounds_error=False)
            out[i] = int_obs

        return out

    def output(self, params):

        params_fixed = self._fixed_params(params)

        if not self.is_surrogate:
            points = (
                np.asarray(self.grid_file.drf_grid), np.asarray(self.grid_file.cfw_grid),
                np.asarray(self.grid_file.stpm_grid),
                np.asarray(self._fid_time_grid),
                np.asarray(self._fid_space_grid))

            interp_mesh = np.array(
                np.meshgrid(params_fixed.drf, params_fixed.cfw, params_fixed.stpm, params_fixed.fid_time,
                            params.fid_space))
            interp_points = abs(np.rollaxis(interp_mesh, 0, 6).reshape((1, 5)))

            out = np.zeros(len(self.stations))
            for i in range(0, len(self.stations)):
                int_obs = interpn(np.asarray(points), self.err_grid[:, :, :, :, :, i], interp_points, method="linear",
                                  bounds_error=False)
                out[i] = int_obs
        else:
            out = np.zeros(len(self.stations))
            for i in range(0, len(self.stations)):
                int_obs = self.k[i].predict([params_fixed.drf, params_fixed.cfw, params_fixed.stpm,params_fixed.fid_time,params_fixed.fid_space])
                out[i] = int_obs

        return out

    def _fixed_params(self, params):
        params_fixed = SWANParams(drf=min(max(params.drf, min(self.grid_file.drf_grid)), max(self.grid_file.drf_grid)),
                                  cfw=min(max(params.cfw, min(self.grid_file.cfw_grid)), max(self.grid_file.cfw_grid)),
                                  stpm=min(max(params.stpm, min(self.grid_file.stpm_grid)),
                                           max(self.grid_file.stpm_grid)),
                                  fidelity_time=min(max(params.fid_time, min(fid_time_range)),
                                           max(fid_time_range)),
                                  fidelity_space=min(max(params.fid_space, min(fid_time_range)),
                                                    max(fid_time_range)))


        return params_fixed

    def output_no_int(self, params):
        drf_idx, cfw_idx, stpm_idx, fid_time_idx, fid_space_idx = self.params_idxs(params=params)

        forecasts = [forecast for forecast in self.grid[drf_idx, cfw_idx, stpm_idx, fid_time_idx, fid_space_idx]]

        out = []
        for forecast, observation in zip(forecasts, self.observations):
            out.append(self.error(forecast, observation))

        return out

    class Forecast:
        def __init__(self, station_idx, forecast_file, range_values=(0, 1)):
            '''

            :param station_idx: Index of a station
            :param forecast_file: Path to file with forecasts
            :param range_values: tuple with relative indexes of a sublist to extract, default = (0, 1) - full list
            '''

            self.station_idx = station_idx
            self.file = forecast_file
            self.range_values = range_values

            assert 0 <= self.range_values[0] <= self.range_values[1] <= 1

            self.hsig_series = self._from_range(self._station_series())

        def _station_series(self):
            hsig_idx = 1
            return [float(line.split(',')[hsig_idx]) for line in self.file.time_series()]

        def _from_range(self, series):
            from_idx = int(len(series) * self.range_values[0])
            to_idx = int(len(series) * self.range_values[1])

            return series[from_idx:to_idx]


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
        return SWANParams(drf=float(csv_row['DRF']), cfw=float(csv_row['CFW']), stpm=float(csv_row['STPM']),fidelity_time=180, fidelity_space=14)


def unique_values(values):
    cnt = Counter(values)
    return list(cnt.keys())
