import csv
import glob
import os
import re
from datetime import datetime

PATH_TO_WW3_RESULTS = '../../samples/ww-res/'


class ObservationFile:
    def __init__(self, path, station_idx):
        self.path = path
        self.station_idx = station_idx

    def time_series(self, from_date="", to_date=""):
        '''
        Extract all wave heights from file with observations for a given time period
        :return: List of wave heights
        '''
        with open(os.path.join(os.path.dirname(__file__), self.path)) as file:
            lines = self._skip_meta_info(file.readlines())
            idx_from, idx_to = self._from_and_to_idxs(lines, from_date, to_date)
            waves = self._wave_heights(time_series=lines[idx_from:idx_to + 1])
            return waves

    def _skip_meta_info(self, lines):
        return list(filter(lambda line: line if not (line.startswith("#") or line.startswith("<")) else None, lines))

    def _from_and_to_idxs(self, lines, from_date="", to_date=""):
        idx_from, idx_to = -1, -1
        for line in lines:
            values = line.split()
            date, time = values[1], values[2]
            resulted_date = FormattedDate().target(date, time)
            if resulted_date == from_date:
                idx_from = lines.index(line)
            if resulted_date == to_date:
                idx_to = lines.index(line)

        assert idx_from < idx_to

        return idx_from, idx_to

    def _wave_heights(self, time_series):
        '''
        Extracting wave heights from time series of observation
        '''
        waves = [float(line.split()[4]) for line in time_series]
        return waves


class ForecastFile:
    def __init__(self, path):
        self.path = path

    def time_series(self):
        with open(self.path) as file:
            lines = self._skip_meta_info(file.readlines())
            return lines

    def _skip_meta_info(self, lines):
        return list(filter(lambda line: line if not line.startswith("%") else None, lines))


class FormattedDate:
    def __init__(self):
        self._source_date_pattern = "%d-%m-%Y %H:%M:%S"
        self._target_date_pattern = "%Y%m%d.%H"
        self._target_suffix = "0000"

    def target(self, date, time):
        return datetime.strptime(" ".join([date, time]), self._source_date_pattern).strftime(
            self._target_date_pattern) + self._target_suffix


class WaveWatchObservationFile:
    FILE_PATTERN = 'obs_fromww_([1-9]).csv'

    def __init__(self, path):
        self.path = path
        self.station_idx = self._parsed_station()

    def time_series(self, **kwargs):
        with open(os.path.join(os.path.dirname(__file__), self.path), newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            results = [float(row['hs']) for row in reader]

            return results

    def _parsed_station(self):
        _, name = os.path.split(self.path)
        p = re.compile(WaveWatchObservationFile.FILE_PATTERN)
        match = p.search(name)

        return match.groups()[0]


def real_obs_from_files():
    files = ["../../samples/obs/1a_waves.txt", "../../samples/obs/2a_waves.txt",
             "../../samples/obs/3a_waves.txt"]
    observations = []

    for station_idx, file in enumerate(files, 0):
        observations.append(ObservationFile(path=file, station_idx=station_idx))

    return observations


def wave_watch_results(path_to_results=PATH_TO_WW3_RESULTS, stations=None):
    '''

    :param path_to_results: Path to directory with ww3 results stored as csv-files
    :param stations: List of stations to take
    :return: List of WaveWatchObservationFiles objects according to chosen stations
    '''

    choice = '|'.join([str(station) for station in stations])
    file_pattern = f'obs_fromww_({choice}).csv'

    files = []
    for file in glob.iglob(os.path.join(path_to_results, '*.csv')):
        if re.search(file_pattern, file):
            files.append(file)

    result = [WaveWatchObservationFile(file) for file in sorted(files)]
    return result
