import logging
import datetime
import os.path

from math import cos, pi

from terra.core.manager import Manager
from terra.ui.grid import CellRenderer
from terra.ui.base import EdjeWidget
from terra.ui.base import Widget
from terra.ui.screen import Screen
from terra.ui.kinetic import KineticMouse
from terra.core.terra_object import TerraObject

mger = Manager()
DownloadManager = mger.get_class("DownloadManager")
download_mger = DownloadManager()

log = logging.getLogger("canola.plugins.images.utils")


def download_file(model, path, url, callback_exists=None, \
      callback_downloaded=None, callback_in_progress=None, attr="downloader"):
    def download_finished(exception, mimetype):
        if exception is None:
            log.debug("Finished download for %s, calling callback" % path)
            callback_downloaded()
        else:
            log.error("Error while downloading file %s from %s, error %s" % \
                                                        (path, url, exception))

    def download_in_progress(exception, mimetype):
        if exception is None:
            callback_in_progress()

    log.debug("Requested file %s" % path)
    downloader = model.__getattribute__(attr)

    if not os.path.exists(path) or os.path.exists(path + ".info"):
        if downloader:
            log.debug("Download for %s already in progress" % path)
            if callback_in_progress:
                downloader.on_finished_add(download_in_progress)
        else:
            log.debug("starting download for " + str(path))
            downloader = download_mger.add(url, path)
            downloader.on_finished_add(download_finished)
            downloader.start(True)
            #model.downloader = downloader
    else:
        log.debug("file %s was already downloaded" % path)
        if callback_exists:
            callback_exists()
    model.__setattr__(attr, downloader)

def gps_valid_coord(value, type=None):
    try:
        value = float(value)
    except ValueError:
        return False

    if type == "lat":
        return value >= -90 and value <= 90
    elif type == "long":
        return value >= -180 and value <= 180
    return True

def gps_get_rectangle(lat, long, radius):
    #diference in km for one degree in latitude, almost constant
    diff_lat = 111.0

    #diference in km for one degree in longitude, decreasing as
    #we aproach the poles
    diff_long = 111.320 * cos(pi*lat/180)

    diff_degree_lat = radius / diff_lat
    diff_degree_long = radius / diff_long

    #coordinates of corners
    W = long - diff_degree_long
    S = lat - diff_degree_lat
    E = long + diff_degree_long
    N = lat + diff_degree_lat

    return (W,S,E,N)

def parse_timestamp(timestamp):
    """ Convert internet timestamp (RFC 3339) into a Python datetime
    object.
    """
    date_str = None
    hour = None
    minute = None
    second = None

    if timestamp.count('T') > 0:
        date_str, time_str = timestamp.split('T')
        time_str = time_str.split('.')[0]
        if time_str.find(':') >= 0:
            hour, minute, second = time_str.split(':')
            if second.endswith('Z'):
                second = second[:-1]
        else:
            hour, minute, second = (time_str[0:2], time_str[2:4], time_str[4:6])
    else:
        date_str = timestamp
        hour, minute, second = 0, 0, 0

    if date_str.find('-') >= 0:
        year, month, day = date_str.split('-')
    else:
        year, month, day = (date_str[0:4], date_str[4:6], date_str[6:8])

    year = int(year)
    month = int(month)
    day = int(day)
    hour = int(hour)
    minute = int(minute)
    second = int(second)

    return datetime.datetime(year, month, day, hour, minute, second)
