import logging
import os.path

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


def download_file(model, path, url, callback_exists=None, callback_downloaded=None, callback_in_progress=None, attr="downloader"):
    def download_finished(exception, mimetype):
        if exception is None:
            log.debug("Finished download for %s, calling callback" % path)
            callback_downloaded()
        else:
            log.error("Error while downloading file %s from %s, error %s" % (path, url, exception))

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
        callback_exists()
    model.__setattr__(attr, downloader)

