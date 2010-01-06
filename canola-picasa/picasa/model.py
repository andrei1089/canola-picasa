#Canola2 Picasa plugin
#Author: Mirestean Andrei < andrei.mirestean at gmail.com >
#
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import edje
import ecore
import logging
import urllib

import thumbnailer
import epsilon

from time import time

from utils import *

from manager import PicasaManager, GpsManager

from terra.core.task import Task
from terra.core.manager import Manager
from terra.core.model import Model, ModelFolder
from terra.core.threaded_func import ThreadedFunction
from terra.core.plugin_prefs import PluginPrefs


manager = Manager()
db = manager.canola_db
picasa_manager = PicasaManager()
gps_manager = GpsManager()

PluginDefaultIcon = manager.get_class("Icon/Plugin")
OptionsActionModel = manager.get_class("Model/Options/Action")
OptionsModelFolder = manager.get_class("Model/Options/Folder")

CanolaError = manager.get_class("Model/Notify/Error")
EntryDialogModel = manager.get_class("Model/EntryDialog")

log = logging.getLogger("plugins.canola-picasa.model")


class Icon(PluginDefaultIcon):
    terra_type = "Icon/Folder/Task/Image/Picasa"
    icon = "icon/main_item/picasa"
    plugin = "picasa"


class MainModelFolder(ModelFolder, Task):
    terra_type = "Model/Folder/Task/Image/Picasa"
    terra_task_type = "Task/Folder/Task/Image/Picasa"

    def __init__(self, parent):
        Task.__init__(self)
        ModelFolder.__init__(self, "Picasa", parent)
        self.callback_notify = None

    def do_load(self):
        picasa_manager.load_thumbler()
        self.threaded_load()

    def threaded_load(self, end_callback=None):
        def refresh():
            picasa_manager.login()

        def refresh_finished(exception, retval):
            if not self.is_loading:
                log.info("model is not loading")
                return

            if exception is not None or not picasa_manager.is_logged():
                msg = "Login error, please check your account details"
                log.error(exception)

                if self.callback_notify:
                    self.callback_notify(CanolaError(msg))

            self.login_successful = picasa_manager.is_logged()
            self.login_error = picasa_manager.get_login_error()

            if self.login_successful:
                UserPicturesModelFolder("My pictures", self)

            CommunityAlbumModelFolder("Search albums by user", self)
            CommunitySearchTag("Search by tag", self, None, True)
            CommunityFeatured("Featured pictures", self, None, True)
            CommunityLocationName("Search by location name", self, None, True)
            GPSSearch(self)

            if end_callback:
                end_callback()

            self.inform_loaded()

        self.is_loading = True
        ThreadedFunction(refresh_finished, refresh).start()

    def do_unload(self):
        ModelFolder.do_unload(self)
        picasa_manager.unload_thumbler()
        gps_manager.stop()

class UserPicturesModelFolder(ModelFolder, Task):
    terra_type = "Model/Folder/Task/Image/Picasa"
    terra_task_type = "Task/Folder/Task/Image/Picasa"

    def do_load(self):
        UserAlbumModelFolder("My albums", self)
        UserAllPicturesModel("All pictures slideshow", self, None, True)

class ImageModel(Model):
    terra_type = "Model/Media/Image/Picasa"

    def __init__(self, name, parent, image, index):

        self.image = image
        self.index = index

        self.id = image.gphoto_id.text
        self.thumb_width = image.media.thumbnail[1].width
        self.thumb_height = image.media.thumbnail[1].height
        self.thumb_url = image.media.thumbnail[1].url

        path = picasa_manager.get_thumbs_path()
        self.thumb_save_path = os.path.join(path, "th_%s.jpg" % str(self.id))

        path = os.path.dirname(path)
        self.path = os.path.join(path, "%s.jpg" % str(self.id))

        self.url = image.media.content[0].url
        self.width = float(image.media.content[0].width)
        self.height = float(image.media.content[0].height)

        self.downloader = None
        self.downloader_thumb = None

        Model.__init__(self, name, parent)

    def delete_model(self):
        ret = picasa_manager.delete_photo(self.image)
        picasa_manager.refresh_user_albums(picasa_manager.user)
        return ret


class AlbumServiceModelFolder(ModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album"

    def __init__(self, name, parent, prop, community=False):
        self.prop = prop
        self.callback_notify = None
        self.callback_update_list = None
        self.size = 0
        self.community = community

        ModelFolder.__init__(self, name, parent)

        self.thumbler = picasa_manager.thumbler

    def request_thumbnail(self, end_callback=None):
        def request(*ignored):
            urllib.urlretrieve(url, path)

        def thumbler_finished_cb(path, thumb_path, w, h):
            del picasa_manager.thumbs_in_progress[path]
            os.rename(thumb_path, path)
            if end_callback:
                end_callback(self)

        def request_finished(exception, retval):
            self.thumbler.request_add(path,
                                           epsilon.EPSILON_THUMB_CROP,
                                           epsilon.EPSILON_THUMB_CROP,
                                           120, 90,
                                           thumbler_finished_cb)

        url = self.prop["thumb_url"]
        path = self.prop["thumb_local"]

        if not url or os.path.exists(path):
            if end_callback:
                try:
                    if picasa_manager.thumbs_in_progress[path]:
                        return
                except KeyError:
                    end_callback(self)

        else:
            open(path, 'w').close()
            picasa_manager.thumbs_in_progress[path] = True
            ThreadedFunction(request_finished, request).start()

    def do_search(self):
        raise NotImplemented("Must be implemented by subclass")

    def do_load(self):
        self.threaded_load()

    def threaded_load(self):
        def refresh():
            return self.do_search()

        def refresh_finished(exception, retval):
            if exception is not None:
                msg = "ERROR!<br> %s" % exception
                log.error(exception)

                if self.callback_notify:
                    self.callback_notify(CanolaError(msg))
            else:
                for pic in retval.entry:
                        self.size += 1
                        ImageModel(pic.title.text, self, pic, self.size-1)
            self.inform_loaded()

        self.size = 0
        self.is_loading = True
        ThreadedFunction(refresh_finished, refresh).start()

    def delete_model(self):
        if self.community:
            self.parent.callback_notify(CanolaError("Can't delete community albums"))
            return False
        else:
            action = picasa_manager.delete_album(self.prop["album_id"])
            log.debug("deleting album with id: %s, operation result: %s" % \
                                                (self.prop["album_id"], action))
            return action

    def options_model_get(self, controller):
        """
        options to change name, description, access should not appear for
        community albums
        """
        if not self.community:
            return PicasaAlbumModelOption(self, controller)
        else:
            return None


class UserAlbumModel(AlbumServiceModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album/UserAlbum"

    def do_search(self):
        return picasa_manager.get_photos_from_album(self.prop["album_id"]);

class UserAllPicturesModel(AlbumServiceModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album/UserAllPictures"

    def do_search(self):
        return picasa_manager.gd_client.GetUserFeed(kind='photo', limit=1000)


class CommunityAlbumModel(AlbumServiceModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album/CommunityAlbum"

    def do_search(self):
        return picasa_manager.get_photos_from_album(self.prop["album_id"], \
                                                       self.prop["album_user"]);


class CommunitySearchTag(AlbumServiceModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album/SearchTag"
    dialog_title = "Search by tag"
    dialog_msg = "Enter tag:"
    dialog_response = None
    show_dialog = True

    def do_search(self):
        print "community do_search"
        return picasa_manager.gd_client.SearchCommunityPhotos( \
                                            self.dialog_response, limit='30')

class GPSSearch(ModelFolder):
    terra_type = "Model/Folder/Image/Picasa/GPSSearch"

    def __init__(self, parent):
        ModelFolder.__init__(self, "Search by GPS location", parent)

    def do_load(self):
        CommunityGPS("Search", self, None, True)
        UpdateGPS("Update GPS location", self)
        CommunityGPSManual("Manual GPS location", self, None, True)


class UpdateGPS(Model):
    terra_type = "Model/Folder/Image/Picasa/GPSSearch/Update"
    show_dialog = False

    def __init__(self, name, parent):
        Model.__init__(self, name, parent)
        self.dialog_queue = None
        self.locked = False

    def update_finished(self):
        print gps_manager.lat
        print gps_manager.long
        dialog = CanolaError("Location available. Lat: %s Long: %s" % \
                                 (str(gps_manager.lat), str(gps_manager.long)))
        if not self.locked:
            self.parent.show_notify(dialog)
        else:
            self.dialog_queue = dialog
        gps_manager.callback_location_updated = None

    def show_dialog(self):
        def unlock(ignored, text):
            self.locked = False
            if self.dialog_queue:
                self.parent.show_notify(self.dialog_queue)
                dialog = self.dialog_queue
                self.dialog_queue = None

        """
        used this lock to avoid the case when the location becomes available
        before the user clicks the ok button of the notify. Trying to show 2
        notifications at the same time generates an error.
        """
        self.locked = True
        self.parent.show_notify(CanolaError("You will be notified when the location is available!",\
                                                        answer_callback=unlock))
        gps_manager.callback_location_updated = self.update_finished
        gps_manager.start()

class CommunityGPSManual(AlbumServiceModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album/GPSManual"
    dialog_title = "GPS Coordonates"
    dialog1_msg = "Enter latitude:"
    dialog2_msg = "Enter longitude:"
    dialog3_msg = "Enter radius:"
    dialog_error = "Invalid coordinates"
    lat = None
    long = None
    radius = None

    def do_search(self):
        bbox =  "%f,%f,%f,%f" % self.rectangle
        return picasa_manager.gd_client.GetFeed("/data/feed/api/all?max-results=50&bbox=%s" % bbox, limit='30')

    def show_dialog2(self, parent, text):
        self.lat = text
        dialog = EntryDialogModel(self.dialog_title, self.dialog2_msg,\
                                    answer_callback=self.show_dialog3)
        self.parent.show_notify(dialog)

    def show_dialog3(self, parent, text):
        self.long = text
        dialog = EntryDialogModel(self.dialog_title, self.dialog3_msg,\
                                    answer_callback=self.show_dialog_finish)
        self.parent.show_notify(dialog)

    def show_dialog_finish(self, parent, text):
        self.radius = text

        #check if input is valid
        if gps_valid_coord(self.lat, "lat") and \
                    gps_valid_coord(self.long, "long") and\
                    gps_valid_coord(self.radius) and \
                    float(self.radius) > 0:
            self.lat = float(self.lat)
            self.long = float(self.long)
            self.radius = float(self.radius)
        else:
            dialog = CanolaError(self.dialog_error)
            self.parent.show_notify(dialog)
            return

        #compute search rectangle based on lat, long, radius
        self.rectangle = gps_get_rectangle(self.lat, self.long, self.radius)
        self.callback_finished()

    def show_dialog(self):
        dialog = EntryDialogModel(self.dialog_title, self.dialog1_msg, answer_callback=self.show_dialog2)
        self.parent.show_notify(dialog)


class CommunityGPS(AlbumServiceModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album/GPS"

    def do_search(self):
        bbox =  "%f,%f,%f,%f" % self.rectangle
        return picasa_manager.gd_client.GetFeed("/data/feed/api/all?max-results=50&bbox=%s" % bbox, limit='30')

    def show_dialog_finished(self, parent, text):
        self.radius = text

        if gps_valid_coord(self.radius) and float(self.radius) > 0:
            self.radius = float(self.radius)
            self.rectangle = gps_get_rectangle(gps_manager.lat,\
                                    gps_manager.long, self.radius)
            self.callback_finished()
        else:
            dialog = CanolaError("Invalid radius")
            self.parent.show_notify(dialog)


    def show_dialog(self):
        if gps_manager.lat is None or gps_manager.long is None:
            self.parent.show_notify(CanolaError("No GPS location. Click Update GPS location first"))
        else:
            dialog = EntryDialogModel("GPS Search", "Enter radius:",\
                                  answer_callback = self.show_dialog_finished)
            self.parent.show_notify(dialog)

class CommunityFeatured(AlbumServiceModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album/Featured"

    def do_search(self):
        return picasa_manager.gd_client.GetFeed("/data/feed/api/featured?max-results=50")


class CommunityLocationName(AlbumServiceModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Service/Album/LocationName"
    dialog_title = "Search by location name"
    dialog_msg = "Enter name:"
    dialog_response = None
    show_dialog = True

    def do_search(self):
        return picasa_manager.gd_client.GetFeed("/data/feed/api/all?max-results=50&l=%s" % self.dialog_response, limit='30')


class ServiceModelFolder(ModelFolder):
    terra_type = "Model/Folder/Task/Image/Picasa/Service"
    empty_msg = "No albums found"

    """
    marks whether or not the albums belong to current user or the community,
    used to disable some options ( delete, add album, change name etc.. )

    """
    community = False

    def __init__(self, name, parent):
        ModelFolder.__init__(self, name, parent)
        self.callback_notify = None
        self.callback_throbber_start = None
        self.callback_throbber_stop = None

    def do_load(self):
        self.search()

    def search(self, end_callback=None):
        del self.children[:]

        def refresh():
            self.do_search()

        def refresh_finished(exception, retval):
            if not self.is_loading:
                log.info("model is not loading")
                return

            if exception is not None:
                msg = "ERROR!<br>" + str(exception[1])
                log.error(exception)

                if self.callback_notify:
                    self.callback_notify(CanolaError(msg))

            if end_callback:
                end_callback()
            self.inform_loaded()

        self.is_loading = True
        ThreadedFunction(refresh_finished, refresh).start()

    def do_search(self):
        raise NotImplementedError("must be implemented by subclasses")

    def parse_entry_list(self, albums):
        for i in albums.entry:
            self._create_model_from_entry(i)

    def _create_model_from_entry(self, album ):

        log.debug("creating model for album_id  %s" % album.gphoto_id.text)
        prop = {}
        prop["album_title"] = album.title.text
        prop["album_id"] = album.gphoto_id.text
        thumb_path = os.path.join(picasa_manager.get_thumbs_path(), \
                                  "%s.jpg" % album.gphoto_id.text)
        prop["thumb_local"]= thumb_path
        prop["thumb_url"] = album.media.thumbnail[0].url
        prop["date"] = album.updated.text[:10]
        prop["access"] = album.access.text
        if  album.summary.text != None  :
            prop["description"] = album.summary.text
        else:
            prop["description"] = "Missing description"

        prop["cntPhotos"] = album.numphotos.text

        if self.community:
            prop["album_user"] = self.dialog_response
            CommunityAlbumModel(album.title.text, self, prop, self.community)
        else:
            UserAlbumModel(album.title.text, self, prop)


class UserAlbumModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Image/Picasa/Service/UserAlbumModel"

    def __init__(self, name, parent):
        ServiceModelFolder.__init__(self, name, parent)

    def do_search(self):
        self.albums = picasa_manager.get_user_albums()
        self.parse_entry_list(self.albums)

    def options_model_get(self, controller):
        return PicasaAlbumModelFolderOption(None, controller)

    def create_album(self, name, desc):
        album = picasa_manager.create_album(name, desc)

        #TODO: find a better way for this
        picasa_manager.refresh_user_albums(picasa_manager.user)

        if album is not None:
            self._create_model_from_entry(album)
            return True
        return False


class CommunityAlbumModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Image/Picasa/Service/CommunityAlbumModel"
    dialog_title = "Community albums"
    dialog_msg = "Enter user name:"
    show_dialog = True

    def __init__(self, name, parent):
        ServiceModelFolder.__init__(self, name, parent)
        self.dialog_response = None
        self.community = True

    def do_search(self):
        if self.dialog_response is not None:
            self.albums = picasa_manager.get_community_albums(self.dialog_response)
            self.parse_entry_list(self.albums)



###########################################
#Settings Model
###########################################

class OptionsModel(ModelFolder):
    terra_type = "Model/Settings/Folder/InternetMedia/Picasa"
    title = "Picasa"

    def __init__(self, parent=None):
        ModelFolder.__init__(self, self.title, parent)

    def do_load(self):
        UserPassOptionsModel(self)
        ClearCacheModel(self)


MixedListItemDual = \
                manager.get_class("Model/Settings/Folder/MixedList/Item/Dual")
class UserPassOptionsModel(MixedListItemDual):
    terra_type = "Model/Settings/Folder/InternetMedia/Picasa/UserPass"
    title = "Login to Picasa"

    def __init__(self, parent=None):
        MixedListItemDual.__init__(self, parent)

    def get_title(self):
        return "User/Password"

    def get_left_button_text(self):
        return "Test login"

    def get_right_button_text(self):
        return "Change"

    def on_clicked(self):
        self.callback_use(self)

    def on_left_button_clicked(self):
        self.callback_use(self)

    def on_right_button_clicked(self):
        self.callback_use(self)


ItemRenderer = manager.get_class("Renderer/EtkList/Item")
class MixedListItem(ModelFolder):
    terra_type = "Model/Settings/Folder/MixedList/Item"
    title = ""

    def __init__(self, parent=None):
        ModelFolder.__init__(self, self.title, parent)

        self.callback_use = None
        self.callback_update = None
        self.callback_killall = None

        self.__create_renderer()

    def __create_renderer(self):
        def _get_state(row):
            return row.get_state()

        def _on_clicked(row, list):
            row.on_clicked()

        self.renderer = ItemRenderer(text_func=_get_state,
                                          item_click=_on_clicked)

    def get_state(self):
        return self.title

    def on_clicked(self):
        raise NotImplementedError("must be implemented by subclasses")

    def do_load(self):
        pass


class ClearCacheModel(MixedListItem):
    terra_type = "Model/Settings/Folder/InternetMedia/Picasa/ClearCache"
    title = "Clear cache"

    def __init__(self, parent=None):
        MixedListItem.__init__(self, parent)
        self.callback_locked = None
        self.cnt = 0
        self.done = False

    def on_clicked(self):
        self.callback_use(self)

    def execute(self):
        self.result = "Cache cleared"
        if self.callback_killall:
            self.callback_killall()

        if self.callback_locked:
            self.callback_locked()

        th_path = picasa_manager.get_thumbs_path()

        for path in [th_path, os.path.dirname(th_path)]:
            try:
                file_list = os.listdir(path)
                for file in file_list:
                    os.remove(os.path.join(path, file))
                    self.cnt += 1
                    if self.cnt % 10 == 0 and self.callback_refresh:
                        self.callback_refresh()
                os.rmdir(path)
            except OSError, e:
                log.error("Error while clearing the cache %s" % e)
                self.result = "ERROR!"
                self.cnt = -1


        if self.cnt >= 0:
            self.result = self.result + "<br> %d files deleted" % self.cnt

        self.done = True
        self.callback_refresh()
        ecore.timer_add(1, self._unlocked_cb)

    def _unlocked_cb(self):
        if self.callback_unlocked:
            self.callback_unlocked()

###########################################
#Options Model
###########################################

class PicasaAddAlbumOptionModel(MixedListItemDual):
    terra_type = "Model/Options/Folder/Image/Picasa/Album/AddAlbum"
    title = "New Album"

    def __init__(self, parent=None):
        MixedListItemDual.__init__(self, parent)
        self.manager = picasa_manager

    def get_title(self):
        return "User/Password"

    def get_left_button_text(self):
        return "Test login"

    def get_right_button_text(self):
        return "Change"

    def on_clicked(self):
        self.callback_use(self)

    def on_left_button_clicked(self):
        self.callback_use(self)

    def on_right_button_clicked(self):
        self.callback_use(self)


MixedListItemOnOff = \
                manager.get_class("Model/Settings/Folder/MixedList/Item/OnOff")
class PhotocastOnOffModel(MixedListItemOnOff):
    terra_type = "Model/Options/Folder/Image/Picasa/Album/PhotocastOnOff"
    title = "Photocasts sync"

    def __init__(self, parent=None):
        MixedListItemOnOff.__init__(self, parent)
        self.parent = parent
        self.title = "Export albums"

    def get_state(self):
        return (self.title, self.parent._state)

    def on_clicked(self):
        self.parent._change_state()
        if self.parent._state:
            self.parent._insert_albums()
        else:
            self.parent._remove_albums()

        self.callback_update(self)


class PhotocastRefreshModel(MixedListItem):
    terra_type = "Model/Options/Folder/Image/Picasa/Album/Photocast/Refresh"
    title = "Refresh"
    message_text = ""

    def __init__(self, parent=None):
        MixedListItem.__init__(self, parent)
        self.callback_locked = None
        self.callback_refresh = None
        self.parent = parent

    def on_clicked(self):
        self.callback_use(self)

    def execute(self):
        if self.parent._state:
            self.parent._remove_albums()
            self.parent._insert_albums()
            self.message_text = "DONE"
        else:
            self.message_text = "Activate sync first"

        if self.callback_refresh:
            self.callback_refresh()

        if self.callback_locked:
            self.callback_locked()
        ecore.timer_add(1.5, self._unlocked_cb)

    def _unlocked_cb(self):
        if self.callback_unlocked:
            self.callback_unlocked()


class PhotocastSyncModel(ModelFolder):
    terra_type = "Model/Options/Folder/Image/Picasa/Album/Photocast"
    title = "Photocasts"
    table = "photocast_feeds"

    stmt_select = "SELECT id, uri, title, desc, author FROM %s" % table
    stmt_delete = "DELETE FROM %s" % table
    stmt_insert = "INSERT INTO %s (uri, title, desc, author, epoch) VALUES \
                                                    ( ?, ?, ?, ?, ?)" % table

    def __init__(self, parent=None):
        ModelFolder.__init__(self, self.title, parent)
        self.prefs = PluginPrefs('picasa')
        try:
            self._state = self.prefs["photocast_sync"]
        except KeyError:
            self._state = False
            self.prefs["photocast_sync"] = self._state
            self.prefs.save()

    def _change_state(self):
        self._state = not self._state
        self.prefs["photocast_sync"] = self._state
        self.prefs.save()

    def _remove_albums(self):
        cur = db.get_cursor()

        self.select_cond = r" WHERE uri LIKE '%" + picasa_manager.user + \
                                            r"%' AND title LIKE '%[PICASA]%'"
        self.query = self.stmt_delete + self.select_cond
        cur.execute(self.query)

        db.commit()
        cur.close()

    def _insert_albums(self):
        cur = db.get_cursor()
        albums = picasa_manager.get_user_albums()

        for album in albums.entry:
            if album.access.text == "protected":
                #TODO: protected albums can't be accessed with authkey
                continue

            name = "[PICASA]" + album.title.text
            try:
                author = album.author[0].name.text
            except:
                author = ""
            description = album.summary.text
            epoch = int(time())
            url = album.id.text.replace("/entry/api/", "/feed/base/", 1) + \
                                                "?kind=photo&alt=rss&hl=en_GB"

            #adding authkey in the url for private and proteced albums
            #authkey seems to be valid for 2 weeks
            if ( album.access.text != "public"):
                auth_index = album.link[0].href.rfind("authkey=")
                auth_key=  album.link[0].href[auth_index:]
                url = url + "&" + auth_key
            try:
                db.execute(self.stmt_insert, (url, name, description, \
                                                                author, epoch))
            except:
                log.error("Error while adding feed in db")

        db.commit()
        cur.close()

    def do_load(self):
        PhotocastOnOffModel(self)
        PhotocastRefreshModel(self)


class PicasaAlbumModelFolderOption(OptionsModelFolder):
    terra_type = "Model/Options/Folder/Image/Picasa"
    title = "Picasa Options"

    def __init__(self, parent, screen_controller=None):
        OptionsModelFolder.__init__(self, parent, screen_controller)

    def do_load(self):
        PicasaAddAlbumOptionModel(self)
        PhotocastSyncModel(self)


class ChangeAlbumNameOptionModel(Model):
    terra_type = "Model/Options/Folder/Image/Picasa/Album/Properties/ChangeName"
    title = "Change name"

    def __init__(self, parent=None):
        self.album_prop = parent.parent.prop
        self.album_model = parent.parent

        self.old_value = self.album_prop["album_title"]

        Model.__init__(self, self.title, parent)

    def update_value(self, new_value):
        if picasa_manager.update_title(self.album_prop["album_id"], new_value):
            self.album_prop["album_title"] = new_value
            self.album_model.parent.callback_update_list(self.album_model)
            return True
        else:
            return False


class ChangeAlbumDescriptionOptionModel(Model):
    terra_type =\
        "Model/Options/Folder/Image/Picasa/Album/Properties/ChangeDescription"
    title = "Change description"

    def __init__(self, parent=None):
        self.album_prop = parent.parent.prop
        self.album_model = parent.parent
        self.old_value = self.album_prop["description"]

        Model.__init__(self, self.title, parent)

    def update_value(self, new_value):
        if picasa_manager.update_desc(self.album_prop["album_id"], new_value):
            self.album_prop["description"] = new_value
            self.album_model.parent.callback_update_list(self.album_model)
            return True
        else:
            return False


class PicasaAlbumModelOption(OptionsModelFolder):
    terra_type = "Model/Options/Folder/Image/Picasa/Album"
    title = "Album Options"

    def __init__(self, parent, screen_controller=None):
        #None parameter instead of parent to avoid updating parent model
        #(AlbumModel) which causes an error(the controller takes
        #PicasaAlbumModelOption as an ImageModel(tries to get it's width)
        OptionsModelFolder.__init__(self, None, screen_controller)
        self.parent = parent

    def do_load(self):
        ChangeAlbumNameOptionModel(self)
        ChangeAlbumDescriptionOptionModel(self)
        AlbumAccessModelFolder(self)


class FullScreenUploadAlbumModel(OptionsActionModel):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaUpload/Submenu"

    def __init__(self, name, parent=None, album_id=None):
        self.name = name
        self.album_id = album_id
        self.parent = parent
        OptionsActionModel.__init__(self, parent)

    def upload(self):
        if not self.album_id:
            res = picasa_manager.create_album(self.name)
            if not res:
                    return (False, "Cannot create new album")
            self.album_id = res.gphoto_id.text

        return picasa_manager.upload_picture(self.parent.image_path,\
                                                            self.album_id)

    def execute(self):
        def upload_finished(exception, retval):
            if exception is not None:
                log.error(exception)
            ret, error = retval
            if not ret:
                self.callback_show_error("FAILED!<br>%s" % error[2])
                log.error("Failed to upload picture %s, exception: %s" % \
                                                (self.parent.image_path, error))
                return
            else:
                self.callback_unlocked()

        self.callback_refresh("uploading")
        self.callback_locked()
        ThreadedFunction(upload_finished, self.upload).start()


class FullScreenUploadOptions(OptionsModelFolder):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaUpload"
    title = "Upload picture to Picasa"

    def __init__(self, parent, screen_controller=None):
        if isinstance(parent.screen_controller.model, AlbumServiceModelFolder):
            log.debug("picasa model detected!disable the Upload option")
            return
        OptionsModelFolder.__init__(self, parent, screen_controller)

    def do_load(self):
        ImageModelFolder = self.parent.screen_controller.model
        ImageModel = ImageModelFolder.children[ImageModelFolder.current]
        self.image_path = ImageModel.path

        albums = picasa_manager.get_user_albums()
        FullScreenUploadAlbumModel("New album" , self)
        for i in albums.entry:
            FullScreenUploadAlbumModel(i.title.text, self, i.gphoto_id.text)


class FullScreenUploadAllOptions(OptionsActionModel):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaUploadAll"
    name = "Upload album to Picasa"

    def __init__(self, parent=None):
        if isinstance(parent.screen_controller.model, AlbumServiceModelFolder):
            return
        OptionsActionModel.__init__(self, parent)
        self.callback_check_cancel = None
        self.callback_show_error = None
        self.callback_unlocked = None
        self.callback_locked = None

    def upload(self):
        album_model = self.screen_controller.model

        if not picasa_manager.is_logged():
            picasa_manager.login()

        if not picasa_manager.is_logged():
            return (False, "User not logged in to Picasa")

        res = picasa_manager.create_album(album_model.name)
        if not res:
            return (False, "Failed to create album")
        album_id = res.gphoto_id.text
        cnt = 0
        total = len(album_model.children)
        self.callback_refresh("uploading<br>0 of %s done" % total)

        for image in album_model.children:
            #user stopped the upload
            if self.callback_check_cancel():
                return (True, None)

            ret, error = picasa_manager.upload_picture(image.path, album_id)
            cnt+=1
            log.info("Uploading picture %s" % image.path)
            if not ret:
                log.error("Failed to upload picture %s, exception: %s" % \
                                                        (image.path, error))
                return (False, "Failed to upload picture %d<br>%s" % \
                                                        (cnt, error[2]) )
            self.callback_refresh("uploading<br>%s of %s done" % (cnt, total))
        return (True, None)

    def execute(self):
        def upload_finished(exception, retval):
            if exception is not None:
                log.error(exception)
            res, error = retval
            if not res:
                self.callback_show_error(error)
                return
            else:
                self.callback_unlocked()

        self.callback_refresh("uploading")
        self.callback_locked()
        ThreadedFunction(upload_finished, self.upload).start()


class FullScreenAddCommentOptions(Model):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaAddComment"
    title = "Add comment"

    def __init__(self, parent=None):
        #comments can't be posted without being logged
        if not isinstance(parent.screen_controller.model,\
                    AlbumServiceModelFolder) or not picasa_manager.is_logged():
            return
        Model.__init__(self, self.title, parent)

    def add_comment(self, comment):
        album_model = self.parent.screen_controller.model
        image_model = album_model.children[album_model.current]
        return picasa_manager.add_comment(image_model.image, comment)


class FullScreenOptions(OptionsModelFolder):
    def get_image_model(self):
        model = self.screen_controller.model
        return model.children[model.current]


class FullScreenImageInfoOptions(FullScreenOptions):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaImageInfo"
    title = "Image Info"

    def __init__(self, parent, screen_controller=None):
        if not isinstance(parent.screen_controller.model,\
                                                    AlbumServiceModelFolder):
            return
        FullScreenOptions.__init__(self, parent, screen_controller)


class FullScreenCommentOptions(FullScreenOptions):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaCommentList/Item"

    def __init__(self, parent, screen_controller=None, prop=None):
        self.prop = prop
        if self.prop is not None:
            self.name = prop["title"]
            self.title = prop["title"]
        FullScreenOptions.__init__(self, parent, screen_controller)


class FullScreenCommentListOptions(FullScreenOptions):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaCommentList"
    title = "Comments"

    def __init__(self, parent, screen_controller=None):
        if not isinstance(parent.screen_controller.model,\
                                                AlbumServiceModelFolder):
            return
        FullScreenOptions.__init__(self, parent, screen_controller)

    def do_load(self):
        def th_func():
            self.load_comments()
        def th_finished(exception, retval):
            self.callback_finished()

        ThreadedFunction(th_finished, th_func).start()


    def load_comments(self):
        image_data = self.get_image_model().image

        list = picasa_manager.get_comments_for_image(image_data)
        self.count = len(list)
        for l in list:
            FullScreenCommentOptions(self, self.screen_controller, l)


class FullScreenDeletePicOptions(OptionsActionModel):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaDelete"
    name = "Delete picture"

    def __init__(self, parent=None):
        if not isinstance(parent.screen_controller.model,\
                                                    AlbumServiceModelFolder):
            return
        #can't delete pictures from community albums
        if parent.screen_controller.model.community:
            return
        OptionsActionModel.__init__(self, parent)

    def execute(self):
        self.callback_delete_pic()


class AlbumAccessModel(Model):
    def __init__(self, name, parent=None):
        Model.__init__(self, name, parent)
        self.name = name
        self.selected = False

    def execute(self):
        print str(self.name) + " clicked"


class AlbumAccessModelFolder(ModelFolder):
    terra_type = "Model/Options/Folder/Image/Picasa/Album/Properties/Access"
    title = "Change access"

    def __init__(self, parent=None):
        ModelFolder.__init__(self, self.title, parent)
        self.album_prop = parent.parent.prop
        self.album_model = parent.parent

    def do_load(self):
        states = ["public", "private", "protected"]
        for i in states:
            child = AlbumAccessModel(i, self)
            if self.album_prop["access"] == i:
                child.selected = True

    def update(self, new_access):
        picasa_manager.update_access(self.album_prop["album_id"], new_access)
        self.album_prop["access"] = new_access
        self.album_model.parent.callback_update_list(self.album_model)

    def do_unload(self):
        self.current = None
        ModelFolder.do_unload(self)
