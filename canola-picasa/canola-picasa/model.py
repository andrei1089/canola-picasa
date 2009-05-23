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

log = logging.getLogger("plugins.canola-picasa.model")

class Icon(PluginDefaultIcon):
    terra_type = "Icon/Folder"
    icon = "icon/main_item/photos_local"
    plugin = "canola-picasa"


class MainModelFolder(ModelFolder, Task):
    terra_type = "Model/Folder/Task/Image/Picasa"
    terra_task_type = "Task/Folder/Task/Image/Picasa"

    def __init__(self, parent):
        Task.__init__(self)
        ModelFolder.__init__(self, "Picasa plugin", parent)

    def do_load(self):
        picasa_manager.login() 
        #print "picasa user = " + str(picasa_manager.getUser())
        #print "picasa password = " + str(picasa_manager.getPassword())
        self.login_successful = picasa_manager.is_logged()
        self.login_error = picasa_manager.get_login_error()

        if self.login_successful == False:
            return 
        AlbumModelFolder("List albums", self)


class xyzModel(ModelFolder):
    terra_type = "Model/Folder/Task/Image/Picasa/Album"
    
    def __init__(self, name, parent):
        ModelFolder.__init__(self, name, parent)

    def request_thumbnail(self, end_callback=None):
        def request(*ignored):
            urllib.urlretrieve(self.thumb_url, self.thumb_local)

        def request_finished(exception, retval):
            if end_callback:
                end_callback()

        if not self.thumb_url or os.path.exists(self.thumb_local):
            if end_callback:
                end_callback()
        else:
            ThreadedFunction(request_finished, request).start()

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
        x = self.do_search()
        #???        
        #for c in x:
        #    self.children.append(c)

    def do_search(self):
        raise NotImplementedError("must be implemented by subclasses")

    def parse_entry_list(self, albums):
        lst = [] 

        for i in albums.entry:
            model = self._create_model_from_entry(i);
            lst.append(model)

        return lst
    
    def _create_model_from_entry(self, album ):
        
        log.debug("creating model for album_id  %s" % album.gphoto_id.text)

        model = xyzModel("album model", self)
        model.album_id = album.gphoto_id.text
        model.thumb_local = os.path.join( picasa_manager.get_thumbs_path(), model.album_id + ".jpg")
        model.thumb_url = album.media.thumbnail[0].url
        model.date = album.updated.text[:10]
        model.name = album.title.text
        if  album.summary.text != None  :
            model.description = album.summary.text
        else:
            model.description = "Missing description"

        model.cntPhotos = album.numphotos.text

        return model

class AlbumModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Image/Picasa/Service/AlbumModel"

    def __init__(self, name,parent):
        ServiceModelFolder.__init__(self, name, parent)
        
      
    def do_search(self):
        self.albums = picasa_manager.get_user_albums()
        return self.parse_entry_list(self.albums)

    def options_model_get(self, controller):
        return PicasaAlbumOptionModel( None, controller )


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
    terra_type = "Model/Options/Folder/Pictures/Picasa/Album/AddAlbum"
    title = "New Album"

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


class PicasaAlbumOptionModel(OptionsModelFolder):
    terra_type = "Model/Options/Folder/Pictures/Picasa"
    title = "Picasa Options"
#    children_prefixes = ["Model/Options/Folder/Pictures/Picasa/Album"]

    def do_load(self):
        PicasaAddAlbumOptionModel(self)
