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
import logging
import urllib
from manager import PicasaManager

from terra.core.task import Task
from terra.core.manager import Manager
from terra.core.model import Model, ModelFolder
from terra.core.threaded_func import ThreadedFunction


manager = Manager()
picasa_manager = PicasaManager()

PluginDefaultIcon = manager.get_class("Icon/Plugin")
OptionsActionModel = manager.get_class("Model/Options/Action")
OptionsModelFolder = manager.get_class("Model/Options/Folder")
CanolaError = manager.get_class("Model/Notify/Error")

log = logging.getLogger("plugins.canola-picasa.model")

class Icon(PluginDefaultIcon):
    terra_type = "Icon/Folder/Task/Image/Picasa"
    icon = "icon/main_item/photos_local"
    plugin = "canola-picasa"


class MainModelFolder(ModelFolder, Task):
    terra_type = "Model/Folder/Task/Image/Picasa"
    terra_task_type = "Task/Folder/Task/Image/Picasa"


    def __init__(self, parent):
        Task.__init__(self)
        ModelFolder.__init__(self, "Picasa plugin", parent)
        self.callback_notify = None

    def do_load(self):
        self.threaded_load()

    def threaded_load(self, end_callback=None):
        def refresh():
            picasa_manager.login()

        def refresh_finished(exception, retval):
            if not self.is_loading:
                log.info("model is not loading")
                return

            #TODO:display specific error messages
            if exception is not None or not picasa_manager.is_logged():
                msg = "ERROR!"
                log.error(exception)

                #why is not workin here???
                if self.callback_notify:
                    self.callback_notify(CanolaError(msg))

            self.login_successful = picasa_manager.is_logged()
            self.login_error = picasa_manager.get_login_error()

            if self.login_successful:
                AlbumModelFolder("List albums", self)

            if end_callback:
                end_callback()

            self.inform_loaded()

        self.is_loading = True
        ThreadedFunction(refresh_finished, refresh).start()

class ImageModel(Model):
    terra_type = "Model/Media/Image/Picasa"

    def __init__(self, name, parent, image):
        self.image = image

        self.path = "/home/andrei/.thumbnails/canola/1aff55242eccf07f2327185b94d69400.jpg"

        self.id = image.gphoto_id.text
        self.thumb_width = image.media.thumbnail[1].width
        self.thumb_height = image.media.thumbnail[1].height
        self.thumb_url = image.media.thumbnail[1].url
        self.thumb_path = picasa_manager.get_thumbs_path() + "/" + str(self.id) + ".jpg"
        self.width = self.thumb_width
        self.height = self.thumb_height

        Model.__init__(self, name, parent)


class AlbumModel(ModelFolder):
    terra_type = "Model/Folder/Image/Picasa/Album"

    def __init__(self, name, parent, prop):
        self.prop = prop
        self.callback_notify = None
        ModelFolder.__init__(self, name, parent)

    def request_thumbnail(self, end_callback=None):
        def request(*ignored):
            urllib.urlretrieve(self.prop["thumb_url"], self.prop["thumb_local"])

        def request_finished(exception, retval):
            if end_callback:
                end_callback()

        if not self.prop["thumb_url"] or os.path.exists(self.prop["thumb_local"]):
            if end_callback:
                end_callback()
        else:
            ThreadedFunction(request_finished, request).start()

    def do_load(self):
        self.threaded_load()

    def threaded_load(self):
        def refresh():
            return picasa_manager.get_photos_from_album(self.prop["album_id"]);

        def refresh_finished(exception, retval):
            #TODO: get specific error
            if exception is not None:
                msg = "ERROR!"
                log.error(exception)

                if self.callback_notify:
                    self.callback_notify(CanolaError(msg))
            else:
                for pic in retval.entry:
                        ImageModel(pic.title.text, self, pic)

            self.inform_loaded()

        self.is_loading = True
        ThreadedFunction(refresh_finished, refresh).start()

    def delete_model(self):
        action = picasa_manager.delete_album(self.prop["album_id"])
        log.debug("deleting album with id: %s, operation result: %s" % (self.prop["album_id"], action) )


class ServiceModelFolder(ModelFolder):
    terra_type = "Model/Folder/Task/Image/Picasa/Service"

    empty_msg = "No albums found"

    def __init__(self, name, parent):
        ModelFolder.__init__(self, name, parent)
        self.callback_notify = None

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
                msg = "ERROR!"
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
        prop["thumb_local"]= os.path.join( picasa_manager.get_thumbs_path(), prop["album_id"] + ".jpg")
        prop["thumb_url"] = album.media.thumbnail[0].url
        prop["date"] = album.updated.text[:10]
        prop["access"] = album.access.text
        if  album.summary.text != None  :
            prop["description"] = album.summary.text
        else:
            prop["description"] = "Missing description"

        prop["cntPhotos"] = album.numphotos.text

        AlbumModel(album.title.text, self, prop)

class AlbumModelFolder(ServiceModelFolder):
    terra_typef = "Model/Folder/Task/Image/Picasa/Service/AlbumModel"

    def __init__(self, name,parent):
        ServiceModelFolder.__init__(self, name, parent)


    def do_search(self):
        self.albums = picasa_manager.get_user_albums()
        self.parse_entry_list(self.albums)

    def options_model_get(self, controller):
        return PicasaAlbumOptionModel( None, controller )

    def create_album(self, name, desc):
        album = picasa_manager.create_album(name, desc)

        #TODO: find a better way for this
        picasa_manager.refresh_user_albums( picasa_manager.getUser() )

        if album is not None:
            self._create_model_from_entry(album)
            return True
        return False


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


MixedListItemDual = manager.get_class("Model/Settings/Folder/MixedList/Item/Dual")
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

class PicasaTestOptionModel(OptionsActionModel):

    name = "Test option"

    def execute(self):
        print "option clicked"

class PicasaAlbumOptionModel(OptionsModelFolder):
    terra_type = "Model/Options/Folder/Image/Picasa"
    title = "Picasa Options"

    def do_load(self):
        PicasaTestOptionModel(self)
        PicasaAddAlbumOptionModel(self)

class FullScreenUploadOptions(OptionsModelFolder):
    terra_type = "Model/Options/Folder/Image/Fullscreen/Submenu/PicasaUpload"
    title = "Upload to Picasa"
