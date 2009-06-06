#
# This file is part of Canola
# Copyright (C) 2007-2009 Instituto Nokia de Tecnologia
# Contact: Renato Chencarek <renato.chencarek@openbossa.org>
#          Eduardo Lima (Etrunko) <eduardo.lima@openbossa.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#

import logging
import os.path

import ecore
import evas
import evas.decorators
import edje
import edje.decorators

from efl_utils.animations import DecelerateTimelineAnimation as TimelineAnimation

from terra.core.manager import Manager
from terra.ui.grid import CellRenderer
from terra.ui.base import EdjeWidget
from terra.ui.base import Widget
from terra.ui.screen import Screen
from terra.ui.kinetic import KineticMouse
from terra.core.terra_object import TerraObject


__all__ = ("ImageInternalScreen",
           "ImageFullScreen",
           "ImageThumbScreen")


mger = Manager()
log = logging.getLogger("canola.plugins.images.ui")
KineticGridWidget = mger.get_class("Widget/KineticGrid")


def calc_max_expand_size(w, h, max_w, max_h):
    if h == 0:
        log.error("Trying to expand image with size 0")
        return 0, 0

    aspect = float(w) / float(h)

    if w > max_w:
        w = max_w
        h = w / aspect

    if h > max_h:
        h = max_h
        w = h * aspect

    return int(w), int(h)


class ImageGridContainer(evas.ClippedSmartObject, Widget):
    def __init__(self, parent, hpadding=1, vpadding=1,
                 halign=0.5, valign=0.5, theme=None):
        Widget.__init__(self, parent, theme)
        evas.ClippedSmartObject.__init__(self, parent.evas)

        self.hpadding = int(hpadding)
        self.vpadding = int(vpadding)
        self._hboxes = []

    def clear_all(self):
        for hbox in self._hboxes:
            hbox.delete()
        self._hboxes = []

    def resize(self, w, h):
        if self.size == (w, h):
            return

        x, y = self.pos
        self._setup_gui(x, y, w, h)

    def rows_set(self, num_rows, w, h):
        for i in xrange(num_rows):
            hbox = ImageHBox(self.evas,
                             hpadding=self.hpadding, valign=0.0)
            # set fixed height
            hbox.resize(0, h)
            self.member_add(hbox)
            hbox.show()
            self._hboxes.append(hbox)

    def num_rows_get(self):
        return len(self._hboxes)

    def row_get(self, row_index):
        return self._hboxes[row_index].children_get()

    def _setup_gui(self, x, y, w, h):
        # invoking parent callback because this resize is called first
        self.parent.callback_resized(x, y, w, h)

        max_row_w, max_h = 0, 0
        for i, hbox in enumerate(self._hboxes):
            max_h = max(max_h, hbox.size[1])
            max_row_w = max(max_row_w, self.parent.row_widths[i])

        for i, hbox in enumerate(self._hboxes):
            # offset to centralize rows
            if hbox.size[0] > w:
                offset_x = (max_row_w - self.parent.row_widths[i]) / 2
            else:
                offset_x = 0
            hbox.move(x + offset_x, y)
            y += max_h + self.vpadding

    def child_get(self, row, index):
        return self._hboxes[row]._children[index]

    def append(self, row, obj):
        self._hboxes[row].append(obj)

    def prepend(self, row, obj):
        self._hboxes[row].prepend(obj)

    def remove(self, row, obj):
        self._hboxes[row].remove(obj)

    def object_at_xy(self, x, y):
        for hbox in self._hboxes:
            if hbox.rect.contains_point(hbox.pos[0], y):
                for c in hbox._children:
                    if c.rect.contains_point(x, y):
                        return c

    def children_move_relative(self, x, y):
        for hbox in self._hboxes:
            hbox.move_relative(x, y)

    def children_leftmost_x(self):
        left_x = 999999
        for hbox in self._hboxes:
            if hbox.pos[0] < left_x:
                left_x = hbox.pos[0]
        return left_x

    def children_rightmost_x(self):
        right_x = 0
        for hbox in self._hboxes:
            if hbox.top_right[0] > right_x:
                right_x = hbox.top_right[0]
        return right_x

    def children_min_right_get(self):
        min_row_right_x = 999999
        min_row_right = None

        for hbox in self._hboxes:
            if hbox.top_right[0] < min_row_right_x:
                min_row_right_x = hbox.top_right[0]
                min_row_right = hbox

        return min_row_right

    def children_max_left_get(self):
        max_row_left_x  = -999999
        max_row_left = None

        for hbox in self._hboxes:
            if hbox.pos[0] > max_row_left_x:
                max_row_left_x = hbox.pos[0]
                max_row_left = hbox

        return max_row_left

    def theme_changed(self):
        for hbox in self._hboxes:
            for c in hbox.children_get():
                c.theme_changed()


class ImageBoxContainer(evas.ClippedSmartObject, Widget):
    def __init__(self, parent, hpadding=1, valign=0.5, theme=None):
        Widget.__init__(self, parent, theme)
        evas.ClippedSmartObject.__init__(self, parent.evas)

        self.hbox = ImageHBox(parent.evas, hpadding, valign=0.5)
        self.valign = valign
        self.member_add(self.hbox)
        self.hbox.show()

        self.center_obj = None

    def clear_all(self):
        for child in self.hbox.children_get():
            child.delete()
        self.hbox.clear()
        self.center_obj = None

    def fixed_height_set(self, h):
        self.hbox.resize(0, h)

    def center_object_set(self, obj):
        if self.center_obj:
            self.center_obj.is_center = False
        obj.is_center = True
        self.center_obj = obj

    def center_object_get(self):
        return self.center_obj

    def center_object_index(self):
        return self.hbox.child_index(self.center_obj)

    def resize(self, w, h):
        if self.size == (w, h):
            return

        x, y = self.pos
        self._setup_gui(x, y, w, h)

    def _setup_gui(self, x, y, w, h):
        log.debug("in setup gui x = %s, y = %s, w = %s, h = %s: " % (x, y, w, h))
        if not self.hbox._children:
            self.clipper.hide()
            return

        self.clipper.visible = self.visible

        center_o_x = self.center_obj.center[0]
        center_s_x = x + (w / 2)
        hbox_x = self.hbox.pos[0]
        cy = int((h - self.hbox.size[1]) * self.valign)
        self.hbox.move(center_s_x - center_o_x + hbox_x, y + cy)

    def append(self, obj):
        self.hbox.append(obj)

    def prepend(self, obj):
        self.hbox.prepend(obj)

    def remove(self, obj):
        self.hbox.remove(obj)

    def child_get(self, index):
        return self.hbox.child_get(index)

    def children_get(self):
        return self.hbox.children_get()

    def animate_relative_to_x(self, offset_x, end_callback):
        def do_transition(value, last_value):
            step = int(value) - last_value[0]
            last_value[0] = int(value)
            self.hbox.move_relative(step, 0)
            if value == offset_x and end_callback:
                end_callback()

        # using last argument for doing relative animation
        animator = TimelineAnimation(0, offset_x, 0.2, do_transition, [0])

    def move_relative_to_x(self, offset_x):
        self.hbox.move_relative(offset_x, 0)

    def theme_changed(self):
        for c in self.children_get():
            c.theme_changed()
            c.update()


class ImageHBox(evas.ClippedSmartObject):
    """Horizontal layout of items."""
    def __init__(self, canvas, hpadding=1, halign=0.5,
                 valign=0.5):
        evas.ClippedSmartObject.__init__(self, canvas)

        self.hpadding = int(hpadding)
        self._children = []
        self.halign = float(halign)
        self.valign = float(valign)

        self._frozen = 0

    def freeze(self):
        self._frozen += 1

    def thaw(self):
        if self._frozen > 1:
            self._frozen -= 1
        elif self._frozen == 1:
            self._frozen = 0
        else:
            log.warning("thaw more than freeze!")

    def move(self, x, y):
        if self._frozen == 0:
            # clipper never resizes nor moves
            clip_pos_x, clip_pos_y = self.clipper.pos
            evas.ClippedSmartObject.move(self, x, y)
            self.clipper.pos_set(clip_pos_x, clip_pos_y)

    def resize(self, w, h):
        pass

    def append(self, obj):
        """Add new child to the end of this box without changing
        the other childs positions.

        @warning: this method will not reconfigure the other objects positions.
        """
        y = self.pos[1]
        h = self.size[1]
        oh = obj.size[1]
        oy = int((h - oh) * self.valign)
        if self._children:
            tail = self._children[-1]
            ox = tail.pos[0] + tail.size[0] + self.hpadding
        else:
            ox = 0

        obj.move(ox, y + oy)

        self.member_add(obj)
        self._children.append(obj)

        self._recalc_size()
        self._recalc_pos()

    def prepend(self, obj):
        """Add new child to the beginning of this box without changing
        the other childs positions.

        @warning: this method will not reconfigure the other objects positions.
        """
        y = self.pos[1]
        h = self.size[1]
        ow, oh = obj.size_get()
        oy = int((h - oh) * self.valign)

        if self._children:
            head = self._children[0]
            ox = head.pos[0] - self.hpadding - ow
        else:
            ox = 0

        obj.move(ox, y + oy)

        self.member_add(obj)
        self._children.insert(0, obj)

        self._recalc_size()
        self._recalc_pos()

    def remove(self, obj):
        """Remove object from this box without changing
        the other childs positions.

        @warning: this method will not reconfigure the other objects positions.
        """
        try:
            self._children.remove(obj)
        except ValueError, e:
            return False

        self.member_del(obj)

        self._recalc_size()
        self._recalc_pos()

        return True

    def clear(self):
        """Remove all children from this box."""
        if not self._children:
            return

        for c in self._children:
            self.member_del(c)
        del self._children[:]

        self._recalc_size()
        self._recalc_pos()

    def children_get(self):
        """Returns an interator over box children.

        @warning: you should not add or remove any object while iterating.

        @return: iterator over children.
        @rtype: iter
        """
        return self._children.__iter__()

    def child_get(self, index):
        return self._children[index]

    def child_index(self, obj):
        return self._children.index(obj)

    def _recalc_size(self):
        if not self._children:
            self.size_set(0, 0)
            return

        left = self._children[0].pos[0]
        right = self._children[-1].top_right[0]

        width = right - left
        self.size_set(width, self.size[1])

    def _recalc_pos(self):
        if not self._children:
            self.move(0, 0)
            return

        x = self._children[0].pos[0]

        self.freeze()
        self.pos_set(x, self.pos[1])
        self.thaw()


class ImageFrameWidget(EdjeWidget):
    def __init__(self, canvas, group_name, parent, theme=None):
        EdjeWidget.__init__(self, canvas, group_name,
                            parent, theme)

        self.image = canvas.FilledImage()
        self.part_swallow("image", self.image)
        self.callback_preloaded = None
        self.image.on_image_preloaded_add(self.cb_preloaded)

        self.model = None

    def model_set(self, model):
        self.model = model

    def model_unset(self):
        self.model = None

    def image_clear(self):
        self.image.image_data_set(None)

    def image_size_set(self, w, h):
        self.image.load_size_set(w, h)

        edje.extern_object_min_size_set(self.image, w, h)
        edje.extern_object_max_size_set(self.image, w, h)

    def hide_image(self):
        self.signal_emit("hide,image", "")

    def image_set(self, file_path):
        try:
            self.image.preload(False)
            self.image.file_set(file_path)
            self.image.hide()
            self.image.preload()
        except evas.EvasLoadError, e:
            log.error("Could not load image: %s" % e)

    def cb_preloaded(self, *args):
        self.image.show()
        if self.callback_preloaded:
            self.callback_preloaded(*args)

    def file_set_cb(self):
        raise NotImplementedError("_file_set_timeout_cb() not implemented")

    @evas.decorators.del_callback
    def _cb_on_delete(self):
        self.image.delete()


class ImageFrameInternal(ImageFrameWidget):
    def __init__(self, canvas, parent, theme=None):
        ImageFrameWidget.__init__(self, canvas,
                                  "images/internal/image_frame",
                                  parent, theme)

        self.throbber = self.part_swallow_get("image_throbber")

        self.is_center = False
        self.callback_mouse_down = None
        self.callback_show_image_finished = None

        def cb(obj):
            self.throbber_stop()
        self.callback_preloaded = cb

    def resize_for_image_size(self, w, h):
        image_w, image_h = calc_max_expand_size(w, h,
                                                self.size_max[0],
                                                self.size_max[1])
        self.image_clear()
        self.image_size_set(image_w, image_h)

        log.debug("setting internal image size, w, h = %s, %s" % (image_w, image_h))

        frame_w = max(image_w, self.size_min[0])
        self.size_set(frame_w, self.size_max[1])

    def file_set_cb(self):
        self.image_set(self.model.path)
        self.update()

    def update(self):
        self.part_text_set("details", self.model.name)
        self.signal_emit("show,image", "")

        if self.is_center:
            self.focus_gain()
        else:
            self.focus_loose()

    def focus_gain(self):
        self.signal_emit("focus,gain", "")

    def focus_loose(self):
        self.signal_emit("focus,loose", "")

    def throbber_start(self):
        self.throbber.signal_emit("throbber,start", "")

    def throbber_stop(self):
        self.throbber.signal_emit("throbber,stop", "")

    @edje.decorators.signal_callback("show,image,finished", "")
    def cb_show_image_finished(self, emission, source):
        self.callback_show_image_finished()

    @edje.decorators.signal_callback("mouse,down,1", "click_area")
    def cb_mouse_down(self, emission, source):
        self.callback_mouse_down(self)


class ImageFrameThumb(ImageFrameWidget):
    def __init__(self, canvas, parent, theme=None):
        ImageFrameWidget.__init__(self, canvas,
                                  "images/thumbnail/image_frame",
                                  parent, theme)

    def resize_for_image_size(self, w, h):
        self.image_clear()

        frame_w = max(w, self.size_min[0])
        frame_h = max(h, self.size_max[1])

        self.image_size_set(w, h)
        self.size_set(frame_w, frame_h)

    def file_set_cb(self):
        if not self.model.thumb_path:
            return

        self.image_set(self.model.thumb_path)
        self.signal_emit("show,image", "")

    @evas.decorators.del_callback
    def _cb_on_delete(self):
        ImageFrameWidget._cb_on_delete(self)


class ImageItemFullscreen(evas.ClippedSmartObject):
    def __init__(self, canvas):
        evas.ClippedSmartObject.__init__(self, canvas)

        self.bg = self.Rectangle()
        self.bg.color = (0, 0, 0, 255)
        self.bg.size = self.size

        self.image = self.FilledImage()
        self.image.show()

        self.bg.show()

        self.geometry_rotated = False
        self.model = None

        self.callback_preloaded = None
        self.image.on_image_preloaded_add(self.cb_preloaded)

    def resize_image(self, w, h):
        image_w, image_h = calc_max_expand_size(w, h,
                                                self.size[0],
                                                self.size[1])
        self.image.size_set(image_w, image_h)
        self.image.center = self.center

        log.debug("setting fullscreen image size %s, w, h = %s, %s"
                  % (self.image.file_get(), image_w, image_h))

    def image_set(self, model, end_callback=None):
        self.model = model
        try:
            self.callback_preloaded = end_callback
            self.image.file_set(model.path)
            self.image.hide()
            self.image.preload()
            self.resize_image(model.width, model.height)

            self.geometry_rotated = False
        except evas.EvasLoadError, e:
            log.error("Could not load image: %s" % e)

    def resize(self, w, h):
        self.bg.size = w, h

    def cb_preloaded(self, *args):
        self.image.show()
        if self.callback_preloaded:
            self.callback_preloaded()


class ImageInternalScreen(Screen):
    view_name = "images_internal"

    def __init__(self, canvas, main_window, title="Photos", theme=None):
        Screen.__init__(self, canvas, "images/internal",
                        main_window, title, theme)
        self._setup_gui()

        self.callback_prev = None
        self.callback_select = None
        self.callback_next = None

        self.callback_transition_in_finished = None
        self.callback_transition_from = None
        self.callback_mouse_move = None
        self.callback_mouse_up = None

        self.animator = None
        self.old_pos = (-1, -1)
        self.max_left = 0
        self.max_right = 0
        self.movement = 0

        event_area = self.part_object_get("click_area")
        event_area.on_mouse_down_add(self._mouse_down_cb)
        event_area.on_mouse_up_add(self._mouse_up_cb)

    def ImageFrameInternal(self, theme=None):
        return ImageFrameInternal(self.evas, self, theme)

    def _setup_gui(self):
        self.image_box = ImageBoxContainer(self, hpadding=40, valign=0.2)
        self.part_swallow("contents", self.image_box)

    def clear_all(self):
        self.image_box.clear_all()

    def theme_changed(self):
        Screen.theme_changed(self)
        self.image_box.theme_changed()

    def transition_from(self, old_view, end_callback=None):
        self.callback_transition_from()
        x, y, w, h = self.image_box.geometry_get()
        self.image_box._setup_gui(x, y, w, h)

        Screen.transition_from(self, old_view, end_callback)

    @edje.decorators.signal_callback("transition,in,finished", "")
    def cb_transition_in_finished(self, emission, source):
        self.callback_transition_in_finished()

    def handle_key_down(self, event):
        # Handle keys while focus is on canvas
        if event.keyname == "Left":
            self.callback_prev()
        elif event.keyname == "Right":
            self.callback_next()
        elif event.keyname in ("F6", "f", "Return"):
            self.callback_select()
        else:
            self._parent_widget.handle_key_down(event)
        return True

    def _mouse_down_cb(self, obj, event_info, *args, **kargs):
        self.old_pos = (-1, -1)
        self.orig_pos = self.evas.pointer_canvas_xy_get()
        i = self.image_box.center_object_index()
        if i == 0:
            self.max_right = 0
        else:
            self.max_right =  self.image_box.center_object_get().center[0] - \
                self.image_box.child_get(i - 1).center[0]

        try:
            self.max_left = self.image_box.center_object_get().center[0] - \
                self.image_box.child_get(i + 1).center[0]
        except IndexError:
            self.max_left = 0

        self.movement = 0
        if self.animator:
            self.animator.delete()
        self.animator = ecore.Animator(self._check_mouse_move_cb)

    def _mouse_up_cb(self, obj, event_info, *args, **kargs):
        self.animator.delete()
        self.animator = None
        if not self.callback_mouse_up:
            return
        if self.movement > 50:
            i = self.image_box.center_object_index()
            self.callback_mouse_up(self.image_box.child_get(i - 1), 1)
        elif self.movement < -50:
            i = self.image_box.center_object_index()
            self.callback_mouse_up(self.image_box.child_get(i + 1), -1)
        else:
            self._check_mouse_click()

    def _check_inside_object(self, x, obj):
        if not obj:
            return False
        x1 = obj.top_left[0]
        x2 = obj.top_right[0]
        return x1 <= x and x <= x2

    def _check_mouse_click(self):
        i = self.image_box.center_object_index()
        center = self.image_box.center_object_get()
        if i == 0:
            left = None
        else:
            left = self.image_box.child_get(i - 1)

        try:
            right = self.image_box.child_get(i + 1)
        except IndexError:
            right = None

        mouse_x = self.evas.pointer_canvas_xy_get()[0]
        sel = center, None
        if self.orig_pos == (-1, -1):
            pass
        elif self._check_inside_object(mouse_x, center):
            sel = center, 0
        elif self._check_inside_object(mouse_x, left):
            sel = left, 1
        elif self._check_inside_object(mouse_x, right):
            sel = right, -1

        self.callback_mouse_up(*sel)

    def _check_mouse_move_cb(self, *args, **kargs):
        if self.old_pos == (-1, -1):
            self.old_pos = self.evas.pointer_canvas_xy_get()
        else:
            new_pos = self.evas.pointer_canvas_xy_get()
            if abs(self.orig_pos[0] - new_pos[0]) > 10:
                self.orig_pos = (-1, -1)
            if self.old_pos == new_pos:
                return True
            d = new_pos[0] - self.old_pos[0]
            if self.movement + d > self.max_right:
                d = self.max_right - self.movement
            if self.movement + d < self.max_left:
                d = self.max_left - self.movement
            self.movement = self.movement + d
            self.old_pos = new_pos
            if self.callback_mouse_move:
                self.callback_mouse_move(d)
        return True

    @evas.decorators.del_callback
    def _cb_on_delete(self):
        self.image_box.delete()


class ImageFullScreen(Screen, TerraObject):
    view_name = "images_fullscreen"
    terra_type = "Model/Media/Image/Fullscreen"

    def __init__(self, canvas, main_window, title="Photos",
                 elements=None, theme=None):
        Screen.__init__(self, canvas, "images/fullscreen",
                        main_window, title, theme)
        self._setup_gui()

        self.elements = elements

        self.throbber = self.part_swallow_get("image_throbber");
        self.controls_right = self.part_swallow_get("fullscreen/controls_right")
        self.controls_left = self.part_swallow_get("fullscreen/controls_left")
        self.controls_visible = False

        self.callback_transition_from = None

        self.callback_mouse_down = None
        self.callback_mouse_up = None
        self.callback_mouse_move = None
        self.callback_rotate_clockwise = None
        self.callback_zoom_in = None
        self.callback_zoom_out = None
        self.callback_prev = None
        self.callback_play_pause_toggle = None
        self.callback_next = None
        self.callback_back = None
        self.callback_show_image_finished = None

    def _setup_gui(self):
        self.image_frame_cur = ImageItemFullscreen(self.evas)
        self.image_frame_new = ImageItemFullscreen(self.evas)

        self._btn_back = EdjeWidget(self.evas, "bt_back_custom", self)
        self._btn_back.hide()
        self._btn_options = EdjeWidget(self.evas, "bt_options_custom", self)
        self._btn_options.hide()

        self._controls_hide_timer = None
        self.prev_image = evas.Image(self.evas)
        self.next_image = evas.Image(self.evas)
        self.prev_image.hide()
        self.next_image.hide()

    def custom_back_button(self):
        return self._btn_back

    def custom_options_button(self):
        return self._btn_options

    def image_prev_preload_cancel(self):
        self.prev_image.preload(True)

    def image_next_preload_cancel(self):
        self.next_image.preload(True)

    def image_prev_next_preload(self, prev, next):
        if prev:
            self.prev_image.file_set(prev.path)
            self.prev_image.preload()
        if next:
            self.next_image.file_set(next.path)
            self.next_image.preload()

    def image_current_get(self):
        return self.image_frame_cur.image

    def image_new_set(self, model, end_callback=None):
        self.part_swallow("image_new", self.image_frame_new)
        self.calc_force()
        self.hide_image()
        self.image_frame_new.image_set(model, end_callback)

    def show_image(self, slideshow=False):
        if slideshow:
            self.signal_emit("show,image,slideshow", "")
        else:
            self.signal_emit("show,image", "")

    def swap_images(self):
        self.part_unswallow(self.image_frame_new)
        self.part_swallow("image_current", self.image_frame_new)
        self.image_frame_cur.hide()

        tmp = self.image_frame_cur
        self.image_frame_cur = self.image_frame_new
        self.image_frame_new = tmp

    @edje.decorators.signal_callback("show,image,finished", "")
    def cb_show_image_finished(self, emission, source):
        self.callback_show_image_finished()

    def hide_image(self):
        self.signal_emit("hide,image", "")

    def play_pause_toggle(self):
        self.controls_right.signal_emit("play_pause,toggle", "")

    def rotate_clockwise(self, end_callback):
        self.rotate(evas.EVAS_IMAGE_ROTATE_270)
        end_callback()

    def rotate(self, rotation):
        image_view = self.image_frame_cur
        if image_view.geometry_rotated:
            w, h = image_view.model.height, image_view.model.width
        else:
            w, h = image_view.model.width, image_view.model.height

        image_view.image.rotate(rotation)
        image_view.resize_image(h, w)
        image_view.geometry_rotated = not image_view.geometry_rotated

    def zoom_in_enable(self):
        self.controls_left.signal_emit("zoom,in,enable", "")

    def zoom_in_disable(self):
        self.controls_left.signal_emit("zoom,in,disable", "")

    def zoom_out_enable(self):
        self.controls_left.signal_emit("zoom,out,enable", "")

    def zoom_out_disable(self):
        self.controls_left.signal_emit("zoom,out,disable", "")

    def loaded(self):
        self._check_has_elements()
        self.throbber_stop()

    def _check_has_elements(self):
        if self.elements:
            self.signal_emit("message,hide", "")
        else:
            self.part_text_set("message", "No items found.")
            self.signal_emit("message,show", "")

    def throbber_start(self):
        self.throbber.signal_emit("throbber,start", "")

    def throbber_stop(self):
        self.throbber.signal_emit("throbber,stop", "")

    def controls_show(self, show_parent_controls=True):
        self.image_controls_show()
        show_parent_controls and self._parent_widget.controls_show()
        self.controls_visible = True
        return False

    def controls_hide(self, hide_parent_controls=True):
        self.image_controls_hide()
        hide_parent_controls and self._parent_widget.controls_hide()
        self.controls_visible = False
        return False

    def controls_invert(self):
        if self.controls_visible:
            self.controls_hide()
        else:
            self.controls_show()

    def image_controls_show(self):
        self.signal_emit("all,show", "")

    def image_controls_hide(self):
        self.signal_emit("all,hide", "")

    def controls_hide_timer_delete(self):
        self._delete_timer(self._controls_hide_timer)

    def controls_hide_timeout(self):
        self.controls_hide_timer_delete()

        self._controls_hide_timer = \
            ecore.timer_add(1.0, self.controls_hide)

    def _delete_timer(self, timer):
        if timer is not None:
            timer.delete()
            timer = None

    # XXX: used by photocast to disable buttons
    def show_buttons_control(self):
        self.controls_right.signal_emit("show,buttons", "")
        self.controls_left.signal_emit("show,buttons", "")

    def hide_buttons_control(self):
        self.controls_right.signal_emit("hide,buttons", "")
        self.controls_left.signal_emit("hide,buttons", "")

    def show_next_control(self):
        self.controls_right.signal_emit("show,next", "")

    def hide_next_control(self):
        self.controls_right.signal_emit("hide,next", "")

    def show_prev_control(self):
        self.controls_right.signal_emit("show,prev", "")

    def hide_prev_control(self):
        self.controls_right.signal_emit("hide,prev", "")

    def theme_changed(self):
        Screen.theme_changed(self)
        self._btn_back.theme_changed()
        self._btn_options.theme_changed()

        self._update_edje_refs()

        # restore hidden state, lost in theme change
        self.hide_image()
        self.controls_show()

    def _update_edje_refs(self):
        self.throbber = self.part_swallow_get("image_throbber");
        self.controls_right = self.part_swallow_get("fullscreen/controls_right")
        self.controls_left = self.part_swallow_get("fullscreen/controls_left")

    def transition_from(self, old_view, end_callback=None):
        self._parent_widget.titlebar_hide()
        self.callback_transition_from()
        Screen.transition_from(self, old_view, end_callback)

    def transition_to(self, new_view, end_callback=None):
        self.controls_hide(hide_parent_controls=False)
        self._parent_widget.titlebar_show()
        Screen.transition_to(self, new_view, end_callback)

    def transition_finished(self, old_view, new_view):
        if self is new_view:
            self.controls_show(show_parent_controls=False)

    @edje.decorators.signal_callback("transition,in,finished", "")
    def cb_transition_in_finished(self, emission, source):
        self.callback_transition_in_finished()

    @edje.decorators.signal_callback("mouse,down,1", "background")
    def cb_mouse_down(self, emission, source):
        x, y = self.evas.pointer_canvas_xy
        self.callback_mouse_down(x, y)

    @edje.decorators.signal_callback("mouse,up,1", "background")
    def cb_mouse_up(self, emission, source):
        x, y = self.evas.pointer_canvas_xy
        self.callback_mouse_up(x, y)

    @edje.decorators.signal_callback("mouse,move", "background")
    def cb_mouse_move(self, emission, source):
        x, y = self.evas.pointer_canvas_xy
        self.callback_mouse_move(x, y)

    @edje.decorators.signal_callback("image,rotate_clock",
                                     "fullscreen/controls_left:")
    def cb_rotate_clockwise(self, emission, source):
        self.callback_rotate_clockwise()

    @edje.decorators.signal_callback("image,zoom,in",
                                     "fullscreen/controls_left:")
    def cb_zoom_in(self, emission, source):
        self.callback_zoom_in()

    @edje.decorators.signal_callback("image,zoom,out",
                                     "fullscreen/controls_left:")
    def cb_zoom_out(self, emission, source):
        self.callback_zoom_out()

    @edje.decorators.signal_callback("image,prev",
                                     "fullscreen/controls_right:")
    def cb_prev(self, emission, source):
        self.callback_prev()

    @edje.decorators.signal_callback("action,clicked",
                                     "fullscreen/controls_right:play_pause,toggle")
    def cb_play_pause(self, emission, source):
        self.callback_play_pause_toggle()

    @edje.decorators.signal_callback("image,next",
                                     "fullscreen/controls_right:")
    def cb_next(self, emission, source):
        self.callback_next()

    @edje.decorators.signal_callback("action,clicked", "back")
    def cb_back(self, emission, source):
        self.callback_back()

    def handle_key_down(self, event):
        # Handle keys while focus is on canvas
        if event.keyname == "Left":
            self.callback_prev()
        elif event.keyname == "Right":
            self.callback_next()
        else:
            self._parent_widget.handle_key_down(event)
        return True

    @evas.decorators.del_callback
    def _cb_on_delete(self):
        self.image_frame_cur.delete()
        self.image_frame_new.delete()
        self._btn_back.delete()
        self._btn_options.delete()
        self.controls_hide_timer_delete()
        self.prev_image.delete()
        self.next_image.delete()


class CellRendererWidget(EdjeWidget, CellRenderer):
    def __init__(self, parent, create_thumb, cancel_thumb, theme=None):
        EdjeWidget.__init__(self, parent.evas, "images/grid_item",
                            parent, theme)
        self._model = None
        self._img = self.evas.FilledImage()
        self._img.on_image_preloaded_add(self._on_preloaded_cb)
        self.part_swallow("contents", self._img)
        self.signal_emit("image,hide", "")
        self.callback_create_thumb = create_thumb
        self.callback_cancel_thumb = cancel_thumb
        self.loading_thumb = False

    @evas.decorators.del_callback
    def on_del(self):
        self._img.delete()

    def theme_changed(self):
        EdjeWidget.theme_changed(self)
        self.force_redraw()

    def force_redraw(self):
        m = self._model
        self._model = None
        self.value_set(m)

    def _on_preloaded_cb(self, *args, **kargs):
        self.signal_emit("image,show", "")

    def _file_set_cb(self, model):
        if self.loading_thumb:
            self.loading_thumb = None
        if model is not self._model:
            return

        x, y, w, h = self._img.geometry_get()
        self._img.load_size_set(w, h)
        try:
            self._img.file_set(model.thumb_path)
            self.signal_emit("image,show", "")
            self._img.preload()
        except Exception, e:
            log.error("could not load image %r: %s", model.thumb_path, e)
            self.signal_emit("image,hide", "")

    def value_set(self, v):
        if self._model is v or v is None:
            return

        if self.loading_thumb:
            self.callback_cancel_thumb(*self.loading_thumb)
            self.loading_thumb = None

        self._model = v
        self._img.preload(True)

        try:
            thumb_path = v.thumb_path
        except AttributeError, e:
            v.thumb_path = None

        x, y, width, height = self.part_geometry_get("gui.draw_area")
        w, h = calc_max_expand_size(self._model.width, self._model.height,
                                    width, height)
        edje.extern_object_min_size_set(self._img, width, height)
        edje.extern_object_max_size_set(self._img, width, height)

        self.signal_emit("image,hide", "")
        if not v.thumb_path or not os.path.exists(v.thumb_path):
            id, cb = self.callback_create_thumb(v, self._file_set_cb)
            if id != None:
                self.loading_thumb = (id, cb)
        else:
            self._file_set_cb(v)


class ImageGridScreen(Screen):
    view_name = "images_grid"

    def __init__(self, canvas, main_window, title="Photos",
                 elements=None, theme=None):
        Screen.__init__(self, canvas, "images/grid", main_window,
                        title, theme)
        self.elements = elements
        self.callback_clicked = None
        self.callback_create_thumb = None
        self.callback_cancel_thumb = None
        self._setup_gui_grid()

    def _setup_gui_grid(self):
        def renderer_new(canvas):
            return CellRendererWidget(self, self._create_thumb, \
                                      self._cancel_thumb)
        self._grid = KineticGridWidget(self, renderer_new, self.elements,
                                       v_align=0.5)
        self._grid.clicked_cb_set(self._cb_clicked)
        self.part_swallow("contents", self._grid)

    def _cb_clicked(self, grid, index):
        self.callback_clicked(self, index)

    def _create_thumb(self, *args):
        if self.callback_create_thumb:
            return self.callback_create_thumb(*args)

    def _cancel_thumb(self, *args):
        if self.callback_cancel_thumb:
            self.callback_cancel_thumb(*args)

    def model_updated(self):
        self._grid.model_updated()

    def loaded(self):
        if not self.elements:
            self.part_text_set("message", "No items found.")
            self.signal_emit("message,show", "")

    def delete(self):
        self._grid.delete()
        self.elements = None
        Screen.delete(self)

    def append(self, child):
        self._grid.append(child)

    def extend(self, children):
        self._grid.extend(children)

    def theme_changed(self):
        Screen.theme_changed(self)
        self._grid.theme_changed()

    def force_redraw(self):
        self._grid.force_redraw()


class ImageThumbScreen(Screen):
    view_name = "images_thumb"

    click_constant = 20
    speed_threshold = 1000

    def __init__(self, canvas, main_window, title="Photos",
                 elements=None, theme=None):
        Screen.__init__(self, canvas, "images/thumbnail",
                        main_window, title, theme)

        self._setup_gui()

        self.elements = elements

        self.throbber = self.part_swallow_get("throbber")

        self.row_widths = []

        self.over_speed = False

        self.kinetic = KineticMouse(self._move_offset)
        self.is_dragging = False
        self.mouse_down_pos = None

        self.callback_block_load = None
        self.callback_resume_load = None

        self.callback_transition_in_finished = None

        self.callback_clicked = None
        self.callback_move_offset = None
        # the resize callback is triggered in ImageGridContainer's _setup_gui
        self.callback_resized = None
        self.callback_on_theme_changed = None

    def ImageFrameThumb(self, theme=None):
        return ImageFrameThumb(self.evas, self, theme)

    def theme_changed(self):
        Screen.theme_changed(self)
        self.image_grid.theme_changed()
        self._setup_click_area()
        self.callback_on_theme_changed()

    def loaded(self):
        self._check_has_elements()
        self.throbber_stop()

    def _check_has_elements(self):
        if self.elements:
            self.signal_emit("message,hide", "")
        else:
            self.part_text_set("message", "No items found.")
            self.signal_emit("message,show", "")

    def throbber_start(self):
        self.throbber.signal_emit("throbber,start", "")

    def throbber_stop(self):
        self.throbber.signal_emit("throbber,stop", "")

    def _setup_gui(self):
        self.image_grid = ImageGridContainer(self,
                                             hpadding=20, vpadding=20)

        self.part_swallow("contents", self.image_grid)
        self._setup_click_area()

    def _setup_click_area(self):
        self.click_area = self.part_object_get("click_area")
        self.click_area.on_mouse_down_add(self._cb_on_mouse_down)
        self.click_area.on_mouse_up_add(self._cb_on_mouse_up)
        self.click_area.on_mouse_move_add(self._cb_on_mouse_move)

    def clear_all(self):
        self.image_grid.clear_all()

    def _check_speed(self, keep_moving):
        if not keep_moving:
            if self.over_speed:
                log.debug("resume load callback")
                if self.callback_resume_load:
                    self.callback_resume_load()
            self.over_speed = False
            return

        if self.kinetic.animation:
            speed = abs(self.kinetic.anim_speed)
            log.debug("abs vel = %s", speed)

            if not self.over_speed and (speed > self.speed_threshold):
                log.debug("hold file sets")
                if self.callback_block_load:
                    self.callback_block_load()
                self.over_speed = True

    def _move_offset(self, offset):
        if not self.callback_move_offset:
            return False

        keep_moving = self.callback_move_offset(offset)
        self._check_speed(keep_moving)

        return keep_moving

    def _emit_clicked(self, x, y):
        obj = self.image_grid.object_at_xy(x, y)
        if obj:
            self.callback_clicked(obj)

    def _is_click_possible(self, x):
        if self.is_dragging or self.mouse_down_pos is None:
            return False
        else:
            return abs(x - self.mouse_down_pos) <= self.click_constant

    def _cb_on_mouse_up(self, obj, event):
        if not event.button == 1:
            return

        x, y = event.position.canvas

        if self._is_click_possible(x):
            self._emit_clicked(x, y)
            self.kinetic.mouse_cancel()
        else:
            self.kinetic.mouse_up(x)

    def _cb_on_mouse_down(self, obj, event):
        if not event.button == 1:
            return

        x, y = event.position.canvas

        self.mouse_down_pos = x
        self.is_dragging = not self.kinetic.mouse_down(x)

    def _cb_on_mouse_move(self, obj, event):
        if not event.buttons == 1:
            return

        x, y = event.position.canvas

        if not self._is_click_possible(x):
            self.is_dragging = True

        self.kinetic.mouse_move(x)

    @edje.decorators.signal_callback("transition,in,finished", "")
    def cb_transition_in_finished(self, emission, source):
        self.callback_transition_in_finished()

    @evas.decorators.del_callback
    def _cb_on_delete(self):
        self.image_grid.delete()

