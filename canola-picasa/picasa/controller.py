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

from terra.core.manager import Manager
from terra.ui.base import PluginThemeMixin
from terra.core.controller import Controller
from terra.core.threaded_func import ThreadedFunction

#TODO: remove this after removing ImageFullscreenController
from terra.core.model import ModelFolder
from terra.core.plugin_prefs import PluginPrefs
from efl_utils.animations import DecelerateTimelineAnimation \
                                        as TimelineAnimation
mouse_move_threshold = 200


from ui import ImageGridScreen
from ui import ImageInternalScreen
from ui import ImageFullScreen

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

        self.delete_button.signal_callback_add("contents_box,collapsed", "",\
                                               cb_collapsed)

    def cb_load_thumbnail(self):
        try:
            self.image.file_set(self._model.prop["thumb_local"])
            self.signal_emit("thumb,show", "")
        except Exception, e:
            log.error("could not load image %r: %s", \
                                self._model.prop["thumb_local"], e)
            self.signal_emit("thumb,hide", "")

    def value_set(self, model):
        """Apply the model properties to the renderer."""
        if not model or model is self._model:
            return

        self._model = model
        self.part_text_set("album_title", model.prop["album_title"])
        self.part_text_set("album_date", "Date: " + model.prop["date"])
        self.part_text_set("album_description", model.prop["description"])
        self.part_text_set("album_cnt_photos", "Photos: " + \
                                                    model.prop["cntPhotos"])
        self.part_text_set("album_access", model.prop["access"].capitalize())
        #TODO: do not modify thumb's l/h ratio
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


class AlbumController(Controller, OptionsControllerMixin):
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
        OptionsControllerMixin.__init__(self)

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

        def down_finished_cb():
            model.thumb_path = model.thumb_save_path
            #TODO: find a way to use the callback instead of force_redraw
            self.force_view_redraw()
            #callback(model)

        def file_exists_cb():
            model.thumb_path = model.thumb_save_path
            callback(model)

        download_file(model, model.thumb_save_path, model.thumb_url, \
                file_exists_cb, down_finished_cb, attr="downloader_thumb")

        return None, None


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
        if self.animating:
            return

        def end(*ignored):
            self.animating = False

        self.model.current = index
        self._thumb_request_cancel_all()
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
        #TODO:
        print "!do_suspend"

    def delete(self):
        #TODO:
        print "!delete"
        #self.thumbler.stop()

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

#TODO: make this class public in canola-core
class ImageFullscreenController(Controller, OptionsControllerMixin):
    terra_type = "Controller/Media/Image"
    click_constant = 20
    default_slideshow_time = 3.0

    def __init__(self, model, canvas, parent):
        if not isinstance(model, ModelFolder):
            self.is_model_folder = False
            model = model.parent
        else:
            self.is_model_folder = True

        Controller.__init__(self, model, canvas, parent)

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

        self.slideshow_loop = False
        self.slideshow_random = False
        self.slideshow_random_idx = 0
        self.slideshow_random_list = []
        OptionsControllerMixin.__init__(self)

    def _load_slideshow_time(self):
        canola_prefs = PluginPrefs("settings")
        try:
            time = int(canola_prefs["slideshow_time"])
        except KeyError:
            time = canola_prefs["slideshow_time"] = self.default_slideshow_time
            canola_prefs.save()
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

    def _model_loaded(self, model):
        self.view.loaded()
        model.callback_loaded = None

    def cb_on_transition_from(self):
        self._setup_view()

    def cb_on_transition_in_finished(self, *ignored):
        if not self.first_transition:
            return

        self.first_transition = False
        self._cmd_emitted()
        model_item = self.model.children[self.model.current]
        self.start_full_throbber(self.view.image_new_set, self.image_preloaded,
                                 model_item)

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

    def image_preloaded(self):
        slideshow_active = self.is_slideshow_active()
        self.stop_full_throbber()
        self.view.show_image(slideshow_active)
        try:
            if self.slideshow_random:
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



