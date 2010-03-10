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
import math
import evas
import ecore
import locale
import logging
import shutil
import os
import random

import epsilon
import thumbnailer

from manager import PicasaManager

from terra.core.manager import Manager
from terra.ui.base import PluginThemeMixin
from terra.core.controller import Controller
from terra.core.threaded_func import ThreadedFunction

#TODO: remove this after removing ImageFullscreenController
from terra.core.model import ModelFolder, Model
from terra.core.plugin_prefs import PluginPrefs
from efl_utils.animations import DecelerateTimelineAnimation \
                                        as TimelineAnimation
mouse_move_threshold = 200

from ui import ImageGridScreen
from ui import ImageInternalScreen
from ui import ImageFullScreen
from ui import ImageThumbScreen
from utils import *

manager = Manager()
DownloadManager = manager.get_class("DownloadManager")
download_mger = DownloadManager()

GeneralActionButton = manager.get_class("Widget/ActionButton")
BaseListController = manager.get_class("Controller/Folder")
BaseRowRenderer =  manager.get_class("Widget/RowRenderer")
ResizableRowRenderer = manager.get_class("Widget/ResizableRowRenderer")
OptionsControllerMixin = manager.get_class("OptionsControllerMixin")
WaitNotifyModel = manager.get_class("Model/WaitNotify")
NotifyModel = manager.get_class("Model/Notify")
OptionsControllerMixin = manager.get_class("OptionsControllerMixin")
ImagesOptionsModelFolder = manager.get_class("Model/Options/Folder/Image/" \
                                              "Fullscreen")
EntryDialogModel = manager.get_class("Model/EntryDialog")
CanolaError = manager.get_class("Model/Notify/Error")

log = logging.getLogger("plugins.canola-picasa.controller")
picasa_manager = PicasaManager()

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
            if self._model.delete_model():
                self._model.parent.is_loading = True
                self._model.parent.callback_state_changed(self._model.parent)
                self._model.parent.children.remove(self._model)

            if self._model.parent.callback_throbber_stop:
                self._model.parent.callback_throbber_stop()

            self.delete_button.signal_emit("unblock,events", "")
            self.delete_button.state_set(ActionButton.STATE_TRASH)

        if self._model.parent.callback_throbber_start:
            self._model.parent.callback_throbber_start()

        self.delete_button.signal_callback_add("contents_box,collapsed", "",\
                                               cb_collapsed)

    def cb_load_thumbnail(self, model):
        try:
            self.image.file_set(model.prop["thumb_local"])
            self.signal_emit("thumb,show", "")
        except Exception, e:
            log.error("could not load image %r: %s", \
                                model.prop["thumb_local"], e)
            self.signal_emit("thumb,hide", "")

    def value_set(self, model):
        """Apply the model properties to the renderer."""
        #TODO: should?? set an "updated" flag for model to avoid the update of all models
        #if not model or model is self._model:
        #    return

        self._model = model
        self.part_text_set("album_title", model.prop["album_title"])
        self.part_text_set("album_date", "Date: " + model.prop["date"])
        self.part_text_set("album_description", model.prop["description"])
        self.part_text_set("album_cnt_photos", "Photos: " + \
                                                    model.prop["cntPhotos"])
        self.part_text_set("album_access", model.prop["access"].capitalize())
        model.request_thumbnail(self.cb_load_thumbnail)

    @evas.decorators.del_callback
    def __on_delete(self):
        """Free internal data on delete."""
        self.image.delete()
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

    This list is like a page result that shows the details for each album.
    """
    terra_type = "Controller/Folder/Task/Image/Picasa/Service"
    row_renderer = RowRendererWidget

    def __init__(self, model, canvas, parent):
        self.empty_msg = model.empty_msg
        BaseListController.__init__(self, model, canvas, parent)
        OptionsControllerMixin.__init__(self)
        self.model.callback_notify = self._show_notify
        self.model.callback_update_list = self._update_ui
        self.model.callback_throbber_start = self.view.throbber_start
        self.model.callback_throbber_stop = self.view.throbber_stop

    def _update_ui(self, model):
        self.view.model_updated()

    def _show_notify(self, err):
        """Popup a modal with a notify message."""
        self.parent.show_notify(err)

    def options_model_get(self):
        try:
            return self.model.options_model_get(self)
        except:
            return None

class MainController(BaseListController):
    terra_type = "Controller/Folder/Task/Image/Picasa"

    def __init__(self, model, canvas, parent):
        model.callback_notify = self._show_notify
        BaseListController.__init__(self, model, canvas, parent)

    def _show_notify(self, err):
        """Popup a modal with a notify message."""
        self.parent.show_notify(err)

    def cb_on_clicked(self, view, index):
        model = self.model.children[index]

        def do_search(ignored, text):
            if text is not None and text != "":
                model.dialog_response = text
                BaseListController.cb_on_clicked(self, view, index)
            else:
                self._show_notify(CanolaError("Empty input"))

        try:
            if model.show_dialog:
                dialog = EntryDialogModel(model.dialog_title, model.dialog_msg,\
                                                    answer_callback=do_search)
                self.parent.show_notify(dialog)
        except:
            BaseListController.cb_on_clicked(self, view, index)

class GPSSearchController(BaseListController):
    terra_type = "Controller/Folder/Image/Picasa/GPSSearch"

    def __init__(self, model, canvas, parent):
        model.show_notify = self._show_notify
        BaseListController.__init__(self, model, canvas, parent)

    def _show_notify(self, err):
        """Popup a modal with a notify message."""
        self.parent.show_notify(err)

    def cb_on_clicked(self, view, index):
        def click_callback():
            BaseListController.cb_on_clicked(self, view, index)

        model = self.model.children[index]
        model.callback_finished = click_callback

        model.show_dialog()

class AlbumController(Controller):
    terra_type = "Controller/Folder/Image/Picasa/Service/Album"

    def __new__(cls, *args, **kargs):
        s = PluginPrefs("settings")
        try:
            value = s["alternative_thumb_screen"]
        except:
            value = False
        if value:
            obj = Controller.__new__(AlbumGridController, *args, **kargs)
        else:
            obj = Controller.__new__(AlbumThumbController, *args, **kargs)

        obj.__init__(*args, **kargs)
        return obj

class AlbumGridController(Controller, OptionsControllerMixin):
    terra_type = "Controller/Folder/Image/Picasa/Service/Album"

    def __init__(self, model, canvas, parent):
        Controller.__init__(self, model, canvas, parent)
        self.animating = False
        #TODO: show throbber while model is loading
        self.model.load()

        self._setup_view()
        self.model.updated = False

        self.thumb_request_list = []

        # should be after setup UI
        self.model.changed_callback_add(self._update_ui)

        self._check_model_loaded()
        OptionsControllerMixin.__init__(self)

        self.thumbler = picasa_manager.thumbler

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
        self.view.callback_clicked = self.cb_on_clicked

    def _cb_create_thumb(self, model, callback):

        def thumbler_finished_cb(path, thumb_path, w, h):
            shutil.move(thumb_path, path)
            model.thumb_path = path
            #TODO: find a way to use the callback instead of force_redraw
            self.force_view_redraw()
            #callback(model)

        def down_finished_cb():
            self.thumbler.request_add(model.thumb_save_path,
                                           epsilon.EPSILON_THUMB_NORMAL,
                                           epsilon.EPSILON_THUMB_CROP,
                                           128, 128,
                                           thumbler_finished_cb)

        def file_exists_cb():
            model.thumb_path = model.thumb_save_path
            callback(model)

        download_file(model, model.thumb_save_path, model.thumb_url, \
                file_exists_cb, down_finished_cb, attr="downloader_thumb")

        return None, None

    def _update_ui(self, model):
        self.view.model_updated()

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
        if self.animating:
            return

        def end(*ignored):
            self.animating = False
        self.model.current = index
        controller = ImageInternalController(self.model, self.view.evas,
                                             self.parent)
        self.animating = True
        self.parent.use(controller, end)

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
        return

    def delete(self):
        for c in self.model.children:
            if c.downloader_thumb is not None:
                download_mger.set_inactive(c.downloader_thumb)
                download_mger._remove_from_manager(c.downloader_thumb)
        self.thumbler.request_cancel_all()
        self.model.changed_callback_del(self._update_ui)
        self.view.delete()
        self.model.unload()

    def options_model_get(self):
        return self.model.options_model_get(self)


class ImageInternalController(Controller):
    terra_type = "Controller/Image"

    def __init__(self, model, canvas, parent):
        Controller.__init__(self, model, canvas, parent)

        self.max_mem_items = 5
        self.num_mem_items = None
        self.animating = False
        self.is_in_transition_out = False
        self.update = False
        self.model.changed_callback_add(self._update_ui)

        self.model.load()

        self._create_view()

    def _create_view(self):
        self.view = ImageInternalScreen(self.evas, self.parent.view,
                                        title=self.model.name)
        self.view.callback_prev = self.prev
        self.view.callback_select = self.select
        self.view.callback_next = self.next
        self.view.callback_mouse_move = self._mouse_move_cb
        self.view.callback_mouse_up = self.cb_on_mouse_up

        self.view.callback_transition_in_finished = \
                                        self.cb_on_transition_in_finished
        self.view.callback_transition_from = self.cb_on_transition_from

    def cb_on_transition_from(self):
        self._setup_view()

    def _update_ui(self, model):
        self.view.model_updated(self.model.size==0)

    def _setup_view(self):
        self.is_in_transition_out = False

        if not self.model.size:
            return

        selected = self.model.current
        items_size = min(self.max_mem_items, self.model.size)
        self.num_mem_items = items_size

        # add selected index
        item = self.model.children[selected]

        image_frame = self.view.ImageFrameInternal()
        self._setup_image_frame(image_frame, item)

        # getting fixed height from ImageFrameInternal
        self.view.image_box.fixed_height_set(image_frame.size_max[1])

        self.view.image_box.append(image_frame)
        self.view.image_box.center_object_set(image_frame)

        num_items = 1
        start_index = selected
        end_index = selected
        self.load_list = [image_frame]
        for offset_index in xrange(1, items_size):
            for off_sig in [1, -1]:
                item_index = selected + (off_sig * offset_index)
                if item_index >= 0 and item_index < self.model.size:
                    item = self.model.children[item_index]
                    image_frame = self.view.ImageFrameInternal()
                    self._setup_image_frame(image_frame, item)
                    self.load_list.insert(0, image_frame)

                    if item_index < selected:
                        self.view.image_box.prepend(image_frame)
                        start_index = item_index
                    else:
                        self.view.image_box.append(image_frame)
                        end_index = item_index

                    num_items += 1
                    if num_items == items_size:
                        break
            if num_items == items_size:
                break

        log.debug("selected: %s" % selected)
        log.debug("start, end: %s, %s" % (start_index, end_index))

        self.start_index = start_index
        self.end_index = end_index

        self.view.show()

    def _setup_image_frame(self, image_frame, model_item):
        image_frame.callback_show_image_finished = \
                                            self.cb_on_show_image_finished

        image_frame.model_set(model_item)
        image_frame.resize_for_image_size(model_item.width, model_item.height)
        image_frame.hide_image()
        image_frame.show()

    def _mouse_move_cb(self, delta, *args, **kargs):
        if self.animating:
            return
        self.view.image_box.move_relative_to_x(delta)

    def cb_on_mouse_up(self, image_frame, direction):
        self.center_at(image_frame, direction)

    def _select_from_ui_index(self, ui_index):
        if ui_index < 0 or ui_index >= self.num_mem_items:
            return

        image_frame = self.view.image_box.child_get(ui_index)
        self.center_at(image_frame)

    def prev(self):
        selected_ui_index = self.model.current - self.start_index
        prev_ui_index = selected_ui_index - 1
        self._select_from_ui_index(prev_ui_index)

    def next(self):
        selected_ui_index = self.model.current - self.start_index
        next_ui_index = selected_ui_index + 1
        self._select_from_ui_index(next_ui_index)

    def select(self):
        selected_ui_index = self.model.current - self.start_index
        self._select_from_ui_index(selected_ui_index)

    def center_at(self, image_frame, direction):
        if self.animating:
            return

        self.animating = True
        self.update = False

        image_center_x = image_frame.image.center[0]
        view_center_x = self.view.image_box.center[0]
        diff_x = view_center_x - image_center_x

        if image_frame == self.view.image_box.center_object_get():
            if direction == None:
                self.view.image_box.animate_relative_to_x(
                    diff_x, self.cb_on_animation_ended)
                return
            self.goto_next_screen(image_frame)
            return

        if direction < 0:
            new_index = image_frame.model.index + (self.num_mem_items / 2)
            self.model.next()
            append = True
        else:
            new_index = image_frame.model.index - (self.num_mem_items / 2)
            self.model.prev()
            append = False

        if new_index >= 0 and new_index < self.model.size:
            if new_index < self.start_index:
                image_frame_reuse = self.view.image_box.child_get(-1)
                self.start_index -= 1
                self.end_index -= 1
                self.update = True
            elif new_index > self.end_index:
                image_frame_reuse = self.view.image_box.child_get(0)
                self.start_index += 1
                self.end_index += 1
                self.update = True

            if self.update:
                new_model_item = self.model.children[new_index]
                self._setup_image_frame(image_frame_reuse, new_model_item)

                self.image_frame_reuse = image_frame_reuse

                # removing image item and then appending/prepending
                self.view.image_box.remove(image_frame_reuse)
                self._remove_from_loading_list(image_frame_reuse)

                if append:
                    self.view.image_box.append(image_frame_reuse)
                else:
                    self.view.image_box.prepend(image_frame_reuse)

        box_x, box_y = self.view.image_box.pos_get()

        old_center = self.view.image_box.center_object_get()
        old_center.focus_loose()
        self.view.image_box.center_object_set(image_frame)
        image_frame.focus_gain()
        self.view.image_box.animate_relative_to_x(diff_x,
                                                  self.cb_on_animation_ended)

    def goto_next_screen(self, image_frame):
        log.debug("Selected centered item of model = %r" % image_frame.model)
        self.is_in_transition_out = True

        fullscreen_controller = ImageFullscreenController(self.model,
                                                          self.evas,
                                                          self.parent)
        self.parent.use(fullscreen_controller,
                        self.cb_on_transition_out_finished)

    def _remove_from_loading_list(self, image_frame):
        if self.load_list:
            try:
                self.load_list.remove(image_frame)
                log.debug("Removed item from loading list")
            except ValueError:
                log.debug("No need to remove current item from loading list")

    def cb_on_animation_ended(self, *ignored):
        if self.update:
            self.load_list.insert(0, self.image_frame_reuse)
            self.file_set()

        self.animating = False

    def cb_on_transition_out_finished(self, parent_cont, model):
        self.hold()

    def cb_on_transition_in_finished(self, *ignored):
        if len(self.load_list) > 0:
            self.start_center_throbber(self.load_list[-1])

    def cb_on_show_image_finished(self):
        self.file_set()

    def start_center_throbber(self, obj):
        if not self.load_list:
            return

        obj.throbber_start()
        self.file_set()

    def file_set(self):
        if not self.load_list or self.is_in_transition_out:
            return
        log.debug("setting child")
        child = self.load_list.pop()
        child.throbber_start()
        child.file_set_cb()

    def hold(self):
        self.view.clear_all()
        self.load_list = []
        self.animating = False

    def delete(self):
        self.model.unload()
        self.view.delete()

    def go_home(self):
        self.hold()
        self.parent.go_home()

    def back(self):
        self.parent.back()


class ImageFullscreenController(Controller, OptionsControllerMixin):
    terra_type = "Controller/Media/Image"
    click_constant = 20

    def __init__(self, model, canvas, parent):
        if not isinstance(model, ModelFolder):
            self.is_model_folder = False
            model = model.parent
        else:
            self.is_model_folder = True

        Controller.__init__(self, model, canvas, parent)

        self.model.changed_callback_add(self._update_ui)
        # mger to disable screen power save during slideshow
        self._mger = Manager()

        self.slideshow_time = self._load_slideshow_time()
        self._slideshow_timer = None

        self.is_loading = False
        self.file_set_idler = None
        self.first_transition = True

        self.zoom_levels = 3
        self.zoom_current = 0
        self.zoom_fit_to_screen = self.zoom_current
        self.is_dragging = False
        self.mouse_down_pos = None

        self._create_view()
        if self.is_model_folder:
            self._setup_model()

        prefs = PluginPrefs("slideshow")
        self.slideshow_loop = prefs.get("loop", False)
        self.slideshow_random = prefs.get("random", False)
        self.slideshow_random_idx = 0
        self.slideshow_random_list = []
        OptionsControllerMixin.__init__(self)

    def _load_slideshow_time(self):
        slideshow_prefs = PluginPrefs("slideshow")

        try:
            self.default_slideshow_time = slideshow_prefs["default_time"]
        except KeyError:
            self.default_slideshow_time = slideshow_prefs["default_time"] = 3.0
            slideshow_prefs.save()

        try:
            time = int(slideshow_prefs["time"])
        except KeyError:
            time = slideshow_prefs["time"] = self.default_slideshow_time
            slideshow_prefs.save()
        return time

    def _setup_model(self):
        self.model.callback_loaded = self._model_loaded
        self.model.load()

    def _create_view(self):
        view = ImageFullScreen(self.evas, self.parent.view,
                               title=self.model.name,
                               elements=self.model.children)

        view.callback_transition_in_finished = self.cb_on_transition_in_finished
        view.callback_transition_from = self.cb_on_transition_from

        view.callback_mouse_down = self.cb_on_mouse_down
        view.callback_mouse_up = self.cb_on_mouse_up
        view.callback_mouse_move = self.cb_on_mouse_move
        view.callback_rotate_clockwise = self.rotate_clockwise
        view.callback_zoom_in = self.zoom_in
        view.callback_zoom_out = self.zoom_out
        view.callback_prev = self.prev
        view.callback_play_pause_toggle = self.play_pause_toggle
        view.callback_next = self.next
        view.callback_back = self.back
        view.callback_show_image_finished = self.cb_on_show_image_finished

        self.view = view

    def _setup_view(self):
        if len(self.model.children) == 0:
            return

        self.zoom_update_view_controls()
        self._check_prev_next_visibility()

    def _check_prev_next_visibility(self):
        if self.model.has_prev():
            self.view.show_prev_control()
        else:
            self.view.hide_prev_control()

        if self.model.has_next():
            self.view.show_next_control()
        else:
            self.view.hide_next_control()

    def _update_ui(self, model):
        self.view.loaded()

    def _model_loaded(self, model):
        self._update_ui(model)
        model.callback_loaded = None
        if model.current is None:
            model.current = 0

        """
        used to prevent an excepton if the user activates random mode
        before the load of the model is finished
        """
        if self.slideshow_random:
            self.slideshow_random_idx = 0
            self.slideshow_random_list = list(enumerate(self.model.children))
            random.shuffle(self.slideshow_random_list)

        self.cb_on_model_load_finished()

    def cb_on_transition_from(self):
        self._setup_view()

    def cb_on_model_load_finished(self):
        self._cmd_emitted()
        model_item = self.model.children[self.model.current]
        self.start_full_throbber(self.view.image_new_set, self.image_preloaded,
                                 model_item)

    def cb_on_transition_in_finished(self, *ignored):
        if not self.first_transition:
            return

        self.first_transition = False
        self.view.throbber_start()
        if not self.model.is_loading:
            self.cb_on_model_load_finished()

    def cb_clicked(self):
        self.stop_slideshow()
        self.view.controls_invert()
        self._check_prev_next_visibility()

    def _is_click_possible(self, x, y):
        if self.mouse_down_pos is None:
            return False

        dist_x = abs(x - self.mouse_down_pos[0])
        dist_y = abs(y - self.mouse_down_pos[1])
        return dist_x**2 + dist_y**2 <= self.click_constant**2

    def cb_on_mouse_down(self, x, y):
        self.is_dragging = True
        self.mouse_down_pos = x, y
        self.prev_x, self.prev_y = x, y

    def cb_on_mouse_up(self, x, y):
        if self._is_click_possible(x, y):
            self.cb_clicked()

        if self.zoom_current == self.zoom_fit_to_screen:
            move = self.mouse_down_pos[0] - self.prev_x
            if abs(move) > mouse_move_threshold:
                if move > 0 and self.model.has_next():
                    self.next()
                elif move < 0 and self.model.has_prev():
                    self.prev()

        self.is_dragging = False
        self.mouse_down_pos = None

    def cb_on_mouse_move(self, x, y):
        if not self.is_dragging:
            return

        if self.zoom_current > self.zoom_fit_to_screen:
            off_x = x - self.prev_x
            off_y = y - self.prev_y

            image = self.view.image_current_get()
            rect = image.rect.move_by(off_x, off_y)
            image.rect = self.clamp_pan_rect(rect, self.view.rect)

        self.prev_x = x
        self.prev_y = y

    def _cmd_emitted(self):
        if self.is_loading:
            return False

        self.stop_slideshow()
        self.is_loading = True

        return True

    def _cmd_finished(self):
        self.is_loading = False

    def _end_reached(self):
        self._cmd_finished()
        self.stop_slideshow()
        self.view.controls_show()

    def restore_zoom_state(self):
        self.zoom_current = self.zoom_fit_to_screen
        self.zoom_update_view_controls()

    def is_slideshow_active(self):
        return self._slideshow_timer is not None

    def start_slideshow_timeout(self):
        self.stop_slideshow_timeout()
        self._slideshow_timer = \
                    ecore.timer_add(self.slideshow_time, self.load_next,
                            self.slideshow_loop, self.image_preloaded)

    def stop_slideshow_timeout(self):
        if self.is_slideshow_active():
            self._slideshow_timer.delete()
            self._slideshow_timer = None
            self._cmd_finished()

    def stop_slideshow(self):
        if self.is_slideshow_active():
            self.view.play_pause_toggle()
            self.view.controls_hide_timer_delete()
            self._restore_screen_powersave()
        self.stop_slideshow_timeout()

    def rotate_clockwise(self):
        if not self._cmd_emitted():
            return

        self.start_full_throbber(self._rotate_process, self.stop_full_throbber)

    def zoom_in(self):
        if self.zoom_current + 1 > self.zoom_levels:
            return

        zoom_current = self.zoom_current
        if not self._cmd_emitted():
            return

        self.zoom_current = zoom_current + 1
        self.zoom_update_view_controls()
        self.zoom(self.view.image_current_get(), 2.0)

    def zoom_out(self):
        if self.zoom_current - 1 < 0:
            return

        zoom_current = self.zoom_current
        if not self._cmd_emitted():
            return

        self.zoom_current = zoom_current - 1
        self.zoom_update_view_controls()
        self.zoom(self.view.image_current_get(), 0.5)

    def zoom(self, image, zoom):
        old_w, old_h = image.size
        new_rect = self.constrain_final_zoom_pos(image, zoom)

        def do_scaling(value):
            scale_factor, center_x, center_y = value

            new_w = int(old_w * scale_factor)
            new_h = int(old_h * scale_factor)

            image.resize(new_w, new_h)
            image.center = (center_x, center_y)

            if scale_factor == zoom:
                self._cmd_finished()

        start_vals = (1, image.rect.center[0], image.rect.center[1])
        end_vals = (zoom, new_rect.center[0], new_rect.center[1])
        animator = TimelineAnimation(start_vals, end_vals, 0.5, do_scaling)

    def constrain_final_zoom_pos(self, image, zoom):
        new_rect = image.rect
        new_rect.w = int(image.size[0] * zoom)
        new_rect.h = int(image.size[1] * zoom)

        center_off_x = self.view.center[0] - image.center[0]
        center_off_y = self.view.center[1] - image.center[1]

        new_rect.center_x = self.view.center[0] - int(center_off_x * zoom)
        new_rect.center_y = self.view.center[1] - int(center_off_y * zoom)

        return self.clamp_pan_rect(new_rect, self.view.rect)

    def clamp_pan_rect(self, pan_rect, fixed_rect):
        if pan_rect.w <= fixed_rect.size[0]:
            pan_rect.center_x = fixed_rect.center[0]
        elif pan_rect.left > fixed_rect.left:
            pan_rect.left = fixed_rect.left
        elif pan_rect.right < fixed_rect.right:
            pan_rect.right = fixed_rect.right

        if pan_rect.h <= fixed_rect.size[1]:
            pan_rect.center_y = fixed_rect.center[1]
        elif pan_rect.top > fixed_rect.top:
            pan_rect.top = fixed_rect.top
        elif pan_rect.bottom < fixed_rect.bottom:
            pan_rect.bottom = fixed_rect.bottom

        return pan_rect

    def zoom_update_view_controls(self):
        if self.zoom_current == self.zoom_fit_to_screen:
            self.view.zoom_out_disable()
        else:
            self.view.zoom_out_enable()

        if self.zoom_current == self.zoom_levels:
            self.view.zoom_in_disable()
        else:
            self.view.zoom_in_enable()

    def prev(self):
        if not self._cmd_emitted():
            return

        self.start_full_throbber(self.load_prev, self.image_preloaded)

    def next(self):
        if not self._cmd_emitted():
            return

        self.start_full_throbber(self.load_next, self.image_preloaded)

    def load_prev(self, end_callback=None):
        try:
            prev_model = self.model.prev()
            self.view.image_next_preload_cancel()
            self.view.image_new_set(prev_model, end_callback)
        except IndexError, ie:
            log.debug("When clicking prev: %s" % ie)
            self._end_reached()
            return False

        self._check_prev_next_visibility()
        return True

    def load_next(self, loop=False, end_callback=None):
        try:
            if self.slideshow_random:
                if loop:
                    self.slideshow_random_idx = self.slideshow_random_idx % \
                                len(self.slideshow_random_list)
                next_model = \
                            self.slideshow_random_list[self.slideshow_random_idx][1]
                log.debug("random_idx = %d, model is %s" %
                          (self.slideshow_random_idx, next_model))
                self.model.current = \
                            self.slideshow_random_list[self.slideshow_random_idx][0]
                self.slideshow_random_idx += 1
            else:
                next_model = self.model.next(loop)
        except IndexError, ie:
            log.debug("When clicking next: %s" % ie)
            self._end_reached()
            return False
        except ZeroDivisionError:
            log.debug("Images list not yet loaded")

        self.view.image_prev_preload_cancel()
        self.view.image_new_set(next_model, end_callback)

        if not loop:
            self._check_prev_next_visibility()

        return False

    def play_pause_toggle(self):
        if self.is_slideshow_active():
            self.pause()
        else:
            self.play()

    def play(self):
        if not self._cmd_emitted():
            return

        self.start_slideshow_timeout()
        self.view.play_pause_toggle()
        self.view.controls_hide_timeout()
        self._disable_screen_powersave()

    def pause(self):
        self.stop_slideshow()

    def start_full_throbber(self, load_image, end_callback, *args):
        self.view.throbber_start()
        load_image(end_callback=end_callback, *args)
    def randomize_slideshow_list(self):
        self.slideshow_random_list = list(enumerate(self.model.children))
        random.shuffle(self.slideshow_random_list)

    def image_preloaded(self):
        slideshow_active = self.is_slideshow_active()
        self.stop_full_throbber()
        self.view.show_image(slideshow_active)
        try:
            if self.slideshow_random:
                if len(self.slideshow_random_list) == 0:
                    self.randomize_slideshow_list()

                if self.slideshow_loop:
                    prev_idx = (self.slideshow_random_idx - 1) % len(self.slideshow_random_list)
                    next_idx = (self.slideshow_random_idx + 1) % len(self.slideshow_random_list)

                    prev = self.slideshow_random_list[prev_idx][1]
                    next = self.slideshow_random_list[next_idx][1]
                else:
                    prev = \
                        self.slideshow_random_list[self.slideshow_random_idx - 1][1]
                    next = \
                        self.slideshow_random_list[self.slideshow_random_idx + 1][1]

            else:
                prev = self.model.prev_get()
                next = self.model.next_get()
        except IndexError, ie:
            log.debug("Reached end of list.")
            return

        self.view.image_prev_next_preload(prev, next)

        if slideshow_active:
            self._slideshow_timer = \
                        ecore.timer_add(self.slideshow_time, self.load_next,
                                self.slideshow_loop, self.image_preloaded)

    def stop_full_throbber(self):
        self.view.throbber_stop()
        return False

    def idler_cb_remove(self):
        if self.file_set_idler:
            self.file_set_idler.delete()

    def idler_cb_add(self, callback, *args):
        if self.file_set_idler:
            return

        self.file_set_idler = ecore.idler_add(self.idler_cb, callback, *args)

    def idler_cb(self, callback, *args):
        callback(*args)
        self.file_set_idler = None

        return False

    def _rotate_process(self, end_callback):
        self.view.rotate_clockwise(end_callback)
        self.restore_zoom_state()
        self._cmd_finished()

    def cb_on_show_image_finished(self):
        self.view.swap_images()
        self.restore_zoom_state()
        self._cmd_finished()

    def _restore_screen_powersave(self):
        if not self._mger.screen_powersave:
            return

        self._mger.screen_powersave.locked = False
        self._mger.screen_powersave.enabled = self._powersave_was_enabled

    def _disable_screen_powersave(self):
        if not self._mger.screen_powersave:
            return

        self._powersave_was_enabled = self._mger.screen_powersave.enabled
        self._mger.screen_powersave.enabled = False
        self._mger.screen_powersave.locked = True

    def hold(self):
        self.idler_cb_remove()
        self.stop_slideshow()

    def delete(self):
        OptionsControllerMixin.delete(self)
        self.idler_cb_remove()
        self.stop_slideshow()
        if self.is_model_folder:
            self.model.unload()
        self.view.delete()

    def go_home(self):
        self.hold()
        self.parent.go_home()

    def back(self):
        self.parent.back()

    def options_model_get(self):
        return ImagesOptionsModelFolder(None, self)


class AlbumThumbController(Controller, OptionsControllerMixin):
    terra_type = "Controller/Folder/Image/Picasa/Service/Album"
    click_constant = 20

    def __init__(self, model, canvas, parent):
        Controller.__init__(self, model, canvas, parent)

        self.reinit()

        self._setup_view()
        self._setup_model()
        self.layout_values = None

        self.fixed_height = self._retrieve_fixed_height()

        self.obj_pool = ObjectPool(20, self.view.ImageFrameThumb)
        self.deleting = False

        OptionsControllerMixin.__init__(self)


    def reinit(self):
        self.threshold_w = 0
        self.row_limit_intervals = []
        self.row_intervals = []

        self.load_list = []
        self.file_set_idler = None


        self.thumb_request_list = []
        self.thumb_request_idler = None

        self.max_left_row = 0
        self.min_right_row = 0


    def _setup_view(self):
        self.view = ImageThumbScreen(self.evas, self.parent.view,
                                     title=self.model.name,
                                     elements=self.model.children)
        self.view.callback_block_load = self.load_list_dequeue_all
        self.view.callback_resume_load = self.load_list_enqueue_all

        self.view.callback_clicked = self._cb_on_clicked
        self.view.callback_move_offset = self._cb_move_offset
        self.view.callback_resized = self._layout_view
        self.view.callback_on_theme_changed = self.cb_on_theme_changed
        self.view.callback_transition_in_finished = \
                                        self.cb_on_transition_in_finished
        self.view.throbber_start()

    def _setup_model(self):
        self.model.callback_loaded = self._model_loaded
        self.model.load()

    def _update_ui(self, model):
        x, y, w, h = self.layout_values
        self.reinit()

        self._setup_view()

        self._layout_view(x, y, w, h)
        self.obj_pool = ObjectPool(20, self.view.ImageFrameThumb)

        self.view.image_grid._setup_gui(x, y, w, h)
        self.view.loaded()


    def _model_loaded(self, model):
        x, y, w, h = self.layout_values
        self.view.image_grid._setup_gui(x, y, w, h)
        self._cb_move_offset(20)
        self.load_list_enqueue_all()
        self.view.loaded()

        model.callback_loaded = None
        self.model.changed_callback_add(self._update_ui)

    def _layout_view(self, x, y, w, h):
        self.layout_values = (x, y, w, h)
        log.debug("in setup view: x = %s, y = %s, w = %s, h = %s" % (x, y ,w, h))
        self.view.clear_all()

        if not self.model.children:
            return
        self.model._sum_thumb_width = 0
        for model_item in self.model.children:
            self._setup_model_item(model_item)
            self.model._sum_thumb_width += model_item.thumb_width

        max_rows = self._calc_max_rows(h, self.fixed_height)

        num_rows, row_width = self._calc_rows_num_width(max_rows,
                                               self.model._sum_thumb_width,
                                                        w)

        log.debug("number of rows in thumb grid = %s, row_width = %s" % \
                                                    (num_rows, row_width))

        if num_rows <= 0:
            return

        # special condition for checking row size before appending image
        no_row_overflow = (row_width == w)

        self.view.image_grid.rows_set(num_rows, w, self.fixed_height)

        current_row = 0
        current_row_width = 0
        self.threshold_w = w * 1.5
        self.row_limit_intervals = []
        self.row_intervals = []
        self.view.row_widths = []
        row_interval_ok = False
        start_index = 0
        # add children to _hboxes
        for i, model_item in enumerate(self.model.children):
            if current_row_width < self.threshold_w:
                image_frame = self.view.ImageFrameThumb()
                self._setup_image_frame(image_frame, model_item, file_set=False)

                if not no_row_overflow:
                    self.view.image_grid.append(current_row, image_frame)
            elif not row_interval_ok:
                self.row_intervals.append((start_index, i - 1))
                row_interval_ok = True

            model_w = model_item.thumb_width

            current_row_width += model_w + self.view.image_grid.hpadding
            if current_row_width > row_width and current_row < num_rows - 1:
                self.view.row_widths.append(current_row_width)
                if no_row_overflow:
                    end_index = i - 1
                    current_row_width = model_w
                else:
                    end_index = i
                    current_row_width = 0

                if not row_interval_ok:
                    self.row_intervals.append((start_index, end_index))

                self.row_limit_intervals.append((start_index, end_index))

                start_index = end_index + 1
                current_row += 1
                row_interval_ok = False

            if no_row_overflow:
                self.view.image_grid.append(current_row, image_frame)

        if len(self.row_limit_intervals) < num_rows:
            # append last row
            self.view.row_widths.append(current_row_width)
            self.row_limit_intervals.append((start_index, i))
            if not row_interval_ok:
                self.row_intervals.append((start_index, i))

        log.debug("row limit intervals = %s" % self.row_limit_intervals)
        log.debug("row intervals = %s" % self.row_intervals)

        self._update_external_rows()

        self.view.show()

    def _setup_image_frame(self, image_frame, model_item, file_set=True):
        image_frame.model_set(model_item)
        model_item.image_frame = image_frame
        image_frame.resize_for_image_size(model_item.thumb_width,
                                          model_item.thumb_height)
        image_frame.hide_image()
        if file_set and not self.view.over_speed:
            self.load_list_enqueue(image_frame)

        image_frame.show()

    def _setup_model_item(self, model_item):
        if self.fixed_height > model_item.height:
            # corner case: avoid generating thumb for small pics
            model_item.thumb_width = model_item.width
            model_item.thumb_height = model_item.height
            model_item.thumb_path = model_item.path
        else:
            model_item.thumb_width = \
                int(self.fixed_height * (model_item.width / float(model_item.height)))
            model_item.thumb_height = self.fixed_height
            model_item.thumb_path = None

    def load_list_enqueue_all(self):
        not_visible_list = []
        num_rows = self.view.image_grid.num_rows_get()
        for row_index in xrange(num_rows):
            row = self.view.image_grid.row_get(row_index)
            for child in row:
                if child.rect.top_left in self.view.rect or \
                   child.rect.top_right in self.view.rect:
                    self.load_list_enqueue(child)
                else:
                    not_visible_list.append(child)

        for child in not_visible_list:
            self.load_list_enqueue(child)
        return False

    def load_list_dequeue_all(self):
        self.load_list = []
        self.thumb_request_list = []

    def load_list_enqueue(self, item):
        # need to generate thumb
        if not item.model.thumb_path:
            self.thumb_request_list_enqueue(item.model)
            return

        self.load_list.append(item)
        self.idler_file_set_add()

    def loading_stop(self):
        self.idler_file_set_remove()
        self.load_list = []

    def idler_file_set_remove(self):
        if self.file_set_idler:
            self.file_set_idler.delete()

        self.file_set_idler = None

    def idler_file_set_add(self):
        if not self.load_list or self.file_set_idler or self.deleting:
            return

        self.file_set_idler = ecore.idler_add(self.idler_file_set_cb)

    def idler_file_set_cb(self):
        if not self.load_list:
            self.file_set_idler = None
            return False

        child = self.load_list.pop(0)

        if not child.model:
            return True

        child.file_set_cb()
        return True

    def thumb_request_list_enqueue(self, model):
        self.thumb_request_list.append(model)
        self.idler_thumb_request_add()

    def idler_thumb_request_remove(self):
        if self.thumb_request_idler:
            self.thumb_request_idler.delete()

        self.thumb_request_idler = None

    def idler_thumb_request_add(self):
        if not self.thumb_request_list or self.thumb_request_idler \
           or self.deleting:
            return
        self.thumb_request_idler = ecore.idler_add(self.idler_thumb_request_cb)

    def idler_thumb_request_cb(self):
        if not self.thumb_request_list:
            self.thumb_request_idler = None
            return False
        model = self.thumb_request_list.pop(0)
        if not model:
            return True

        def down_finished_cb():
            model.thumb_path = model.thumb_save_path
            if model.image_frame:
                self.load_list_enqueue(model.image_frame)

            self.thumb_request_idler = None
            self.idler_thumb_request_add()

        def file_exists():
            model.thumb_path = model.thumb_save_path
            if model.image_frame:
                self.load_list_enqueue(model.image_frame)

            self.thumb_request_idler = None
            self.idler_thumb_request_add()

        download_file(model, model.thumb_save_path, model.thumb_url, \
                file_exists, down_finished_cb, attr="downloader_thumb")

        return False

    def _retrieve_fixed_height(self):
        dummy_iframe = self.view.ImageFrameThumb()
        result = dummy_iframe.size_max[1]
        dummy_iframe.delete()
        return result

    def _calc_rows_num_width(self, max_rows, total_width, min_row_width):
        if total_width <= 0 or max_rows <= 0:
            return (0, 0)

        total_pad_width = total_width + (self.model.size - 1) \
                          * self.view.image_grid.hpadding

        row_width = total_pad_width / max_rows
        row_width = max(row_width, min_row_width)

        if total_pad_width < max_rows * min_row_width:
            num_rows = int(math.ceil(total_pad_width / float(row_width)))
        else:
            num_rows = max_rows

        return num_rows, row_width

    def _calc_max_rows(self, total_h, items_max_h):
        if items_max_h <= 0:
            return 0

        max_rows = total_h / (items_max_h + self.view.image_grid.vpadding)

        return max_rows

    def _next_model_item(self, row):
        current = self.view.image_grid.child_get(row, -1)
        current_index = current.model.index

        if current_index >= self.row_limit_intervals[row][1]:
            return None

        return self.model.children[current_index + 1]

    def _prev_model_item(self, row):
        current = self.view.image_grid.child_get(row, 0)
        current_index = current.model.index

        if current_index <= self.row_limit_intervals[row][0]:
            return None

        return self.model.children[current_index - 1]

    def _update_row_interval(self, row, offset_start, offset_end):
        cur_start, cur_end = self.row_intervals[row]
        self.row_intervals[row] = cur_start + offset_start, cur_end + offset_end

    def _update_external_rows(self):
        self.min_right_row = self.view.image_grid.children_min_right_get()
        self.max_left_row = self.view.image_grid.children_max_left_get()

    def _image_frame_clear(self, image_frame):
        image_frame.hide_image()
        image_frame.model.image_frame = None
        image_frame.model_unset()

    def expand_block_left(self):
        updated = False
        expand_width = 150

        for row, hbox in enumerate(self.view.image_grid._hboxes):
            width = 0
            row_expand_width = expand_width - \
                abs(hbox.pos[0] - self.max_left_row.pos[0])

            while width < row_expand_width:
                if not self.expand_left(row):
                    break

                updated = True
                new_obj = hbox.child_get(0)
                width += new_obj.image.size[0] + self.view.image_grid.hpadding

            if updated:
                row_width = hbox.top_right[0] - hbox.pos[0]
                row_retreat_width = row_width - self.threshold_w

                self.retreat_right(row, row_retreat_width)

        self._update_external_rows()

        return updated

    def expand_left(self, row):
        prev_model = self._prev_model_item(row)
        if not prev_model:
            return False

        self._update_row_interval(row, -1, 0)

        log.debug("expanding left row = %s" % row)
        image_frame = self.obj_pool.get()
        self._setup_image_frame(image_frame, prev_model)

        self.view.image_grid.prepend(row, image_frame)

        return True

    def retreat_left(self, row, retreat_width):
        row_width = 0
        log.debug("retreating left")

        head = self.view.image_grid._hboxes[row].child_get(0)
        while retreat_width > 0 and head.top_right[0] < 0:
            self.view.image_grid.remove(row, head)
            self._update_row_interval(row, 1, 0)
            retreat_width -= (self.view.image_grid.hpadding + head.size[0])
            self._image_frame_clear(head)
            self.obj_pool.release(head)
            head = self.view.image_grid._hboxes[row].child_get(0)

    def expand_block_right(self):
        updated = False
        expand_width = 150

        for row, hbox in enumerate(self.view.image_grid._hboxes):
            width = 0
            row_expand_width = expand_width - \
                abs(hbox.top_right[0] - self.min_right_row.top_right[0])

            while width < row_expand_width:
                if not self.expand_right(row):
                    break

                updated = True
                new_obj = hbox.child_get(-1)
                width += new_obj.image.size[0] + self.view.image_grid.hpadding

            if updated:
                row_width = hbox.top_right[0] - hbox.pos[0]
                row_retreat_width = row_width - self.threshold_w
                self.retreat_left(row, row_retreat_width)

        self._update_external_rows()

        return updated

    def expand_right(self, row):
        next_model = self._next_model_item(row)
        if not next_model:
            return False

        self._update_row_interval(row, 0, 1)

        log.debug("expanding right row = %s" % row)
        image_frame = self.obj_pool.get()
        self._setup_image_frame(image_frame, next_model)

        self.view.image_grid.append(row, image_frame)

        return True

    def retreat_right(self, row, retreat_width):
        row_width = 0
        log.debug("retreating right")

        tail = self.view.image_grid._hboxes[row].child_get(-1)
        while retreat_width > 0 and tail.pos[0] > self.view.size[0]:
            self.view.image_grid.remove(row, tail)
            self._update_row_interval(row, 0, -1)
            retreat_width -= (self.view.image_grid.hpadding + tail.size[0])
            self._image_frame_clear(tail)
            self.obj_pool.release(tail)
            tail = self.view.image_grid._hboxes[row].child_get(-1)

    def _cb_move_offset(self, offset_x):
        if offset_x == 0 or not self.model.children:
            return False

        result = True
        border_offset = 100
        expand_offset = 400

        if offset_x < 0:
            view_right_x = self.view.top_right[0]
            row_new_right_x = self.min_right_row.top_right[0] + offset_x

            if row_new_right_x < view_right_x + expand_offset:
                if self.expand_block_right():
                    row_new_right_x = self.min_right_row.top_right[0] + offset_x
                    if row_new_right_x < view_right_x:
                        offset_x = view_right_x - self.min_right_row.top_right[0]
                        self.expand_block_right()
                else:
                    grid_right_x = self.view.image_grid.children_rightmost_x()
                    grid_new_right_x = grid_right_x + offset_x

                    if grid_new_right_x < view_right_x - border_offset:
                        offset_x = min(0, view_right_x - border_offset - grid_right_x)
                        result = False
        else:
            view_left_x = self.view.pos[0]
            row_new_left_x = self.max_left_row.pos[0] + offset_x

            if row_new_left_x > view_left_x - expand_offset:
                if self.expand_block_left():
                    row_new_left_x = self.max_left_row.pos[0] + offset_x
                    if row_new_left_x > view_left_x:
                        offset_x = view_left_x - self.max_left_row.pos[0]
                        self.expand_block_left()
                else:
                    grid_left_x = self.view.image_grid.children_leftmost_x()
                    grid_new_left_x = grid_left_x + offset_x

                    if grid_new_left_x > view_left_x + border_offset:
                        offset_x = max(0, view_left_x + border_offset - grid_left_x)
                        result = False

        self.view.image_grid.children_move_relative(offset_x, 0)

        return result

    def goto_next_screen(self, image_frame):
        log.debug("Clicked in item of model = %r" % image_frame.model)
        # setting model folder current index
        self.model.current = image_frame.model.index

        self.load_list_dequeue_all()

        internal_controller = ImageInternalController(self.model,
                                                      self.evas,
                                                      self.parent)
        self.parent.use(internal_controller)

    def _cb_on_clicked(self, image_frame):
        self.goto_next_screen(image_frame)

    def cb_on_transition_in_finished(self, *ignored):
        ecore.timer_add(1.0, self.load_list_enqueue_all)

    def cb_on_theme_changed(self):
        for obj in self.obj_pool.free_objs_iter():
            obj.theme_changed()

    def delete(self):
        self.deleting = True
        self.load_list_dequeue_all()
        self.obj_pool.delete()
        self.model.changed_callback_del(self._update_ui)
        self.model.unload()
        self.view.delete()

    def back(self):
        self.parent.back()

    def go_home(self):
        self.parent.go_home()

    def options_model_get(self):
        return self.model.options_model_get(self)


class ObjectPool(object):
    def __init__(self, num_pre_allocate, generator, *args, **kargs):
        self.free_objs = []
        self.generator = generator
        self.args = args
        self.kargs = kargs

        self.pre_allocate(num_pre_allocate)

    def pre_allocate(self, num_objs):
        for i in xrange(num_objs):
            obj = self.create_instance()
            self.free_objs.insert(0, obj)

    def create_instance(self):
        obj = self.generator(*self.args, **self.kargs)
        return obj

    def get(self):
        if not self.free_objs:
            return self.create_instance()

        return self.free_objs.pop(0)

    def release(self, obj):
        self.free_objs.insert(0, obj)

    def delete(self):
        for obj in self.free_objs:
            obj.delete()

    def free_objs_iter(self):
        return self.free_objs.__iter__()

class UserAllPicturesController(ImageFullscreenController):
    terra_type = "Controller/Folder/Image/Picasa/Service/Album/UserAllPictures"

