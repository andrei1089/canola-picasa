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

import evas
import ecore
import locale
import logging
import os

#TODO: remove this
import urllib

from terra.core.manager import Manager
from terra.ui.base import PluginThemeMixin
from terra.core.controller import Controller
from terra.core.threaded_func import ThreadedFunction

from ui import ImageGridScreen

manager = Manager()
GeneralActionButton = manager.get_class("Widget/ActionButton")
BaseListController = manager.get_class("Controller/Folder")
BaseRowRenderer =  manager.get_class("Widget/RowRenderer")
ResizableRowRenderer = manager.get_class("Widget/ResizableRowRenderer")
OptionsControllerMixin = manager.get_class("OptionsControllerMixin")
WaitNotifyModel = manager.get_class("Model/WaitNotify")
NotifyModel = manager.get_class("Model/Notify")
OptionsControllerMixin = manager.get_class("OptionsControllerMixin")

log = logging.getLogger("plugins.canola-picasa.controller")


class ActionButton(PluginThemeMixin, GeneralActionButton):
    plugin = "picasa"


class GeneralRowRenderer(PluginThemeMixin, BaseRowRenderer):
    """
    This renderer is applied on ServiceController. Providing
    a personalized list item for albums. It shows the following album
    properties: title, thumb, number of pictures, data it was created.

    @note: This renderer extends BaseRowRenderer, overloading
    some methods.

    @note: An instance of this class can be reused to show properties
    of diferent models due to optimizations. So, to take full advantages
    of this feature, you can load heavy data like images, on value_set method,
    only keeping in the models the path to load the data. This has a nice
    effect with memory usage and is very scalable. For example if you have a
    list with 6 renderers, and your list has 800 images, only 6 images are
    stored in memory, not 800 (generally the number of renderers is close to
    the number of visible items on the list).

    @note: To tell Canola to look first on the plugin theme you have to
    add PluginThemeMixin class and set the plugin variable with the plugin
    name.

    @see: ServiceController, BaseRowRenderer, PluginThemeMixin
    """
    plugin = "picasa"

    def __init__(self, parent, theme=None):
        BaseRowRenderer.__init__(self, parent, theme)
        self.image = self.evas.FilledImage()
        self.part_swallow("contents", self.image)
        self.signal_emit("thumb,hide", "")

        self.bg_selection = self.PluginEdjeWidget("widget/list/bg_selection")
        self.part_swallow("selection", self.bg_selection)

        self.delete_button = ActionButton(self)
        self.delete_button.state_set(ActionButton.STATE_TRASH)
        self.delete_button.on_button_delete_pressed_set(self.cb_delete_pressed)
        self.part_swallow("delete_button", self.delete_button)

        self.delete_button.on_contents_box_expanded_set(self.cb_box_expanded)
        self.delete_button.on_contents_box_collapsed_set(self.cb_box_collapsed)
        self.delete_button.disable_download()

    def theme_changed(self, end_callback=None):
        def cb(*ignored):
            self.part_swallow("selection", self.bg_selection)
            self.part_swallow("delete_button", self.delete_button)
            self.part_swallow("contents", self.image)
            if end_callback is not None:
                end_callback(self)

        self.bg_selection.theme_changed()
        self.delete_button.theme_changed()
        self.delete_button.state_set(ActionButton.STATE_TRASH)
        self.delete_button.disable_download()

        BaseRowRenderer.theme_changed(self, cb)

    def cb_box_expanded(self, *ignored):
        self._model.selected_state = True

    def cb_box_collapsed(self, *ignored):
        self._model.selected_state = False

    def cb_delete_pressed(self, *ignored):
        def cb_collapsed(*ignored):
            self.delete_button.signal_callback_del("contents_box,collapsed", "",
                                                   cb_collapsed)
            #TODO: ? Delete_model in thread ?
            self._model.delete_model()
            self._model.parent.children.remove(self._model)

            self.delete_button.signal_emit("unblock,events", "")
            self.delete_button.state_set(ActionButton.STATE_TRASH)

        self.delete_button.signal_callback_add("contents_box,collapsed", "",
                                               cb_collapsed)

    def cb_load_thumbnail(self):
        try:
            self.image.file_set(self._model.prop["thumb_local"])
            self.signal_emit("thumb,show", "")
        except Exception, e:
            log.error("could not load image %r: %s", self._model.prop["thumb_local"], e)
            self.signal_emit("thumb,hide", "")

    def value_set(self, model):
        """Apply the model properties to the renderer."""
        if not model or model is self._model:
            return

        self._model = model
        self.part_text_set("album_title", model.prop["album_title"])
        self.part_text_set("album_date", "Date:" + model.prop["date"])
        self.part_text_set("album_description", model.prop["description"])
        self.part_text_set("album_cnt_photos", "Photos: "+ model.prop["cntPhotos"] )
        self.part_text_set("album_access", model.prop["access"].capitalize() )
        #TODO: do not modify thumb's l/h ratio
        model.request_thumbnail(self.cb_load_thumbnail)

    @evas.decorators.del_callback
    def __on_delete(self):
        """Free internal data on delete."""
        self.image.delete()
        #self.rating_area.delete()
        self.bg_selection.delete()
        self.delete_button.delete()


class ResizableRowRendererWidget(GeneralRowRenderer, ResizableRowRenderer):
    """Picasa Base List Item Renderer for Selected Items.

    This renderer is very similar with RowRendererWidget. The diference
    is the select animation that it starts.

    @see: ServiceController, RowRendererWidget
    """
    row_group="list_item_picasa_resizeable"

    def __init__(self, parent, theme=None):
        GeneralRowRenderer.__init__(self, parent, theme)


class RowRendererWidget(GeneralRowRenderer):
    row_group="list_item_picasa"
    resizable_row_renderer = ResizableRowRendererWidget


class ServiceController(BaseListController, OptionsControllerMixin):
    """Picasa Album List.

    This list is like a page result that shows the videos that match
    with some criteria.

    @note: This class extends BaseListController, but apply a different
    item renderer declaring a row_renderer variable and a different
    screen interface declaring a list_group variable. The group "list_video"
    is the interface of the default Canola video list.

    @see: BaseListController, RowRendererWidget,
          SelectedRowRendererWidget
    """
    terra_type = "Controller/Folder/Task/Image/Picasa/Service"
    row_renderer = RowRendererWidget
    list_group = "list_video"

    def __init__(self, model, canvas, parent):
        self.empty_msg = model.empty_msg
        BaseListController.__init__(self, model, canvas, parent)
        OptionsControllerMixin.__init__(self)
        self.model.callback_notify = self._show_notify

    def _show_notify(self, err):
        """Popup a modal with a notify message."""
        self.parent.show_notify(err)

    def options_model_get(self):
        return self.model.options_model_get(self)


class AlbumController(Controller):
    terra_type = "Controller/Folder/Image/Picasa/Album"

    def __init__(self, model, canvas, parent):
        Controller.__init__(self, model, canvas, parent)
        self.animating = False
        self.model.load()
        self._setup_view()
        self.model.updated = False

        self.thumb_request_list = []

        # should be after setup UI
        self.model.changed_callback_add(self._update_ui)

        self._check_model_loaded()

    def do_resume(self):
        if self.model.updated:
            self.model.updated = False
            self.view.force_redraw()

    def _check_model_loaded(self):
        if self.model.is_loaded:
            self.view.loaded()
        else:
            self.model.callback_loaded = self._model_loaded

    def _model_loaded(self, model):
        self.view.loaded()
        self.model.callback_loaded = None

    def _setup_view(self):
        title = self.model.name
        self.view = ImageGridScreen(self.evas, self.parent.view, title,
                              self.model.children)
        self.view.callback_create_thumb = self._cb_create_thumb
        self.view.callback_cancel_thumb = self._thumb_request_cancel
        self.view.callback_clicked = self.cb_on_clicked

    def _cb_create_thumb(self, model, callback):
        #TODO: load thumb with downloadmanager, use thumbnailer to crop picture
        print "!!!!!!" + model.thumb_path
        print str(model.thumb_width) + " " + str(model.thumb_height)
        if not os.path.exists(model.thumb_path):
            urllib.urlretrieve(model.thumb_url, model.thumb_path)

        callback(model)
        return None, None
    #if self._thumb_fetch_from_db(model):
        #    if os.path.exists(model.thumb_path):
        #        callback(model)
        #        return None, None
        #return self._thumb_request(model, callback)

    def _thumb_request(self, model, callback):
        if not model:
            return True

        def _thumb_request_cb(path, thumb_path, w, h):
            log.debug("Thumbnailer callback called with: %s", path)
            if thumb_path:
                model.thumb_path = thumb_path
                model.thumb_width = w
                model.thumb_height = h
                try:
                    stat_thumb = os.stat(thumb_path)
                except OSError, e:
                    return True
                r = self._db.execute("REPLACE INTO thumbnails VALUES (" \
                                     "%d, '%s', %d, %d, %d )" % \
                                     (model.id, thumb_path, w, h,
                                      stat_thumb.st_mtime))
                r.close()
                callback(model)
            else:
                log.warning("Could not generate image thumb for %s", \
                            model.path)

        id = None
        if self.thumbler:
            id = self.thumbler.request_add(model.path,
                                           epsilon.EPSILON_THUMB_NORMAL,
                                           epsilon.EPSILON_THUMB_CROP,
                                           128, 128,
                                           _thumb_request_cb)

        return id, _thumb_request_cb

    def _thumb_request_cancel(self, *args, **kargs):
        print "thumb request cancel"
        #self.thumbler.request_cancel(*args)

    def _thumb_request_cancel_all(self, *args, **kargs):
        print "thumb request cancel all"
        #self.thumbler.request_cancel_all(*args)

    #def _thumb_fetch_from_db(self, model):
    #    try:
    #        r = self._db.execute("SELECT * FROM thumbnails WHERE id = %d" \
            #                             % model.id)
    #    except sqlite3.OperationalError, e:
    #        log.error("table 'thumbnails' doesn't exist")

    #    row = r.fetchone()
    #    r.close()
    #    if row:
    #        id, path, width, height, mtime = row
    #        if model.mtime <= mtime:
    #            model.thumb_path = path
    #            model.thumb_width = width
    #            model.thumb_height = height
    #            return True

    #    return False

    def _update_ui(self, model):
        self.view.model_updated()

    def delete(self):
        self.model.changed_callback_del(self._update_ui)
        self.view.delete()
        self.model.unload()
        self._db.commit()
        self._db.close()

    def back(self):
        if self.animating:
            return

        def end(*ignored):
            self.animating = False

        self.animating = True
        self.parent.back(end)

    def cb_on_animation_ended(self, *ignored):
        self.animating = False

    def cb_on_clicked(self, view, index):
        print "image clicked"
        #if self.animating:
        #    return

        #def end(*ignored):
        #    self.animating = False

        #self.model.current = index
        #self._thumb_request_cancel_all()
        #controller = ImageInternalController(self.model, self.view.evas,
        #                                     self.parent)
        #self.animating = True
        #self.parent.use(controller, end)

    def go_home(self):
        self.parent.go_home()

    def force_view_redraw(self):
        self.view.force_redraw()

    def reset_model(self):
        self.view.freeze()
        for c in self.model.children:
            c.reset()
        self.view.thaw()

    def do_suspend(self):
        print "!do_suspend"

    def delete(self):
        print "!delete"
        #self.thumbler.stop()


