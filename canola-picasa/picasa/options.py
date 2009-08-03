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
import etk
import ecore
import evas.decorators
import logging

from time import gmtime, strftime

from terra.core.controller import Controller
from terra.core.manager import Manager
from terra.core.terra_object import TerraObject
from terra.core.threaded_func import ThreadedFunction
from terra.ui.modal import Modal
from terra.ui.throbber import EtkThrobber
from terra.ui.panel import PanelContentFrame
from terra.ui.base import PluginEdjeWidget
from terra.ui.base import PluginThemeMixin
from manager import PicasaManager
from utils import parse_timestamp

manager = Manager()
picasa_manager = PicasaManager()

ModalController = manager.get_class("Controller/Modal")
PanelContentModal = manager.get_class("Widget/Settings/PanelContentModal")
UsernamePasswordModal = \
                    manager.get_class("Widget/Settings/UsernamePasswordModal")
MixedListController = manager.get_class("Controller/Settings/Folder/MixedList")

log = logging.getLogger("plugins.canola-picasa.options")

###########################################################
#Settings
###########################################################

class OptionsController(MixedListController):
    terra_type = "Controller/Settings/Folder/InternetMedia/Picasa"

class MessageView(Modal):
    def __init__(self, parent, title):
        Modal.__init__(self, parent.view, title,
                       parent.view.theme, hborder=16,
                       vborder=20)

        self.title = ""
        self.embed = etk.Embed(self.evas)
        self.throbber = EtkThrobber(title)
        self.throbber.show()
        self.throbber_align = \
            etk.Alignment(0.5, 0.4, 0.0, 0.0, child=self.throbber)
        self.throbber_align.show()
        self.embed.add(self.throbber_align)
        self.embed.show()
        self.contents = self.embed.object

    def message(self, hide_cb=None):
        self.throbber.callback_animate_hide_finished = hide_cb
        self.throbber.start()
        self.show()
        self.half_expand()

    @evas.decorators.del_callback
    def _destroy_message(self):
        self.embed.destroy()
        self.embed = None

class ClearCacheController(ModalController):
    terra_type = "Controller/Settings/Folder/InternetMedia/Picasa/ClearCache"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)

        model.callback_locked = self.start
        model.callback_unlocked = self.stop
        model.callback_killall = self.parent.killall
        model.callback_refresh = self.update_text

        self.view = MessageView(parent, model.title)
        self.model.execute()

    def start(self):
        self.view.message(hide_cb=self.stop)
        self.model.callback_locked = None

    def stop(self):
        def cb():
            self.parent.back()
        self.view.hide(cb)

    def update_text(self):
        if not self.model.done:
            self.view.throbber.text_set("%d files deleted" % self.model.cnt)
        else:
            self.view.throbber.text_set(self.model.result)

    def delete(self):
        self.view.delete()
        self.view = None
        self.model.result = None
        self.model.callback_locked = None
        self.model.callback_unlocked = None
        self.model.callback_killall = None
        self.model.callback_refresh = None

class UserPassController(ModalController):
    terra_type = "Controller/Settings/Folder/InternetMedia/Picasa/UserPass"

    def __init__(self, model, canvas, parent):

        ModalController.__init__(self, model, canvas, parent)
        self.parent_controller = parent
        self.model = model
        self.view = UsernamePasswordModal(parent, "Login to Picasa",
                                          parent.view.theme,
                                          vborder=50)

        picasa_manager.reload_prefs()
        self.view.username = picasa_manager.user
        self.view.password = picasa_manager.password

        self.view.callback_ok_clicked = self._on_ok_clicked
        self.view.callback_cancel_clicked = self.close
        self.view.callback_escape = self.close
        self.view.show()

    def close(self):
        def cb(*ignored):
            self.parent_controller.view.list.redraw_queue()
            self.back()
        self.view.hide(end_callback=cb)

    def _on_ok_clicked(self):
        if not self.view.username or not self.view.password:
            return

        picasa_manager.user = self.view.username
        picasa_manager.password = self.view.password
        def refresh(session):
            session.login()

        def refresh_finished(exception, retval):
            def cb_close(*ignored):
                self.close()
                self.parent.killall()

            if picasa_manager.is_logged():
                self.model.title = "Logged as %s" % picasa_manager.user
                self.view.message("Login successful")
                ecore.timer_add(1.5, cb_close)

            else:
                self.view.message("Login error:<br>%s" % \
                                            picasa_manager.get_login_error())
                ecore.timer_add(1.5, cb_close)

        self.view.message_wait("Trying to login...")
        ThreadedFunction(refresh_finished, refresh, picasa_manager).start()

    def delete(self):
        self.view.delete()
        self.view = None
        self.model = None


###########################################################
#Options
###########################################################

class NewAlbumModal(PanelContentModal):
    terra_type = "Widget/Settings/NewAlbumModal"

    def __init__(self, parent, title,
                 theme=None, hborder=16, vborder=50):
        PanelContentModal.__init__(self, parent, title, theme,
                                   hborder=hborder, vborder=vborder)

        label_name = etk.Label("Name:")
        label_name.alignment_set(0.0, 1.0)
        label_name.show()

        label_description = etk.Label("Description:")
        label_description.alignment_set(0.0, 1.0)
        label_description.show()

        self.entry_name = etk.Entry(text="")
        self.entry_name.on_text_activated(self._on_ok_clicked)
        self.entry_name.show()

        self.entry_description = etk.Entry(text="")
        self.entry_description.on_text_activated(self._on_ok_clicked)
        self.entry_description.show()

        vbox = etk.VBox()
        vbox.border_width_set(5)
        vbox.append(label_name, etk.VBox.START, etk.VBox.FILL, 5)
        vbox.append(self.entry_name, etk.VBox.START, etk.VBox.FILL, 10)

        vbox.append(label_description, etk.VBox.START, etk.VBox.FILL, 5)
        vbox.append(self.entry_description, etk.VBox.START, etk.VBox.FILL, 10)
        vbox.show()

        self.set_content(vbox)

    def get_name(self):
        return self.entry_name.text

    def set_name(self, text):
        self.entry_name.text = text

    name = property(get_name, set_name)

    def get_description(self):
        return self.entry_description.text

    def set_description(self, text):
        self.entry_description.text = text

    description = property(get_description, set_description)

    def _on_ok_clicked(self, *ignored):
        if self.callback_ok_clicked:
            self.callback_ok_clicked()


class PicasaAddAlbumOptionController(ModalController):
    terra_type = "Controller/Options/Folder/Image/Picasa/Album/AddAlbum"
    def __init__(self, model, canvas, parent):

        ModalController.__init__(self, model, canvas, parent)

        self.parent_controller = parent
        self.model = model

        self.view = NewAlbumModal(parent.last_panel, "Add new album")
        self.view.callback_ok_clicked = self._on_ok_clicked
        self.view.callback_cancel_clicked = self.close
        self.view.callback_escape = self.close
        self.view.show()

    def close(self):
        def cb(*ignored):
            self.back()
            self.parent.back()
        self.view.hide(end_callback=cb)

    def _on_ok_clicked(self):
        def cb_close(*ignored):
            self.close()

        def th_function():
            AlbumModelFolder = self.parent.screen_controller.model

            return AlbumModelFolder.create_album(self.view.name, \
                                                        self.view.description)
        def th_finished(exception, retval):
           if not retval:
                self.view.message_wait("Failed to add new album")
                ecore.timer_add(2, cb_close)
                return
           self.close()

        if not self.view.name:
            self.view.message_wait("Missing name")
            ecore.timer_add(2, cb_close)
            return

        self.view.message_wait("please wait")
        ThreadedFunction(th_finished, th_function).start()

    def delete(self):
        self.view.delete()
        self.view = None
        self.model = None

MixedListController = manager.get_class("Controller/Settings/Folder/MixedList")
class PhotocastSyncController(MixedListController):
    terra_type = "Controller/Options/Folder/Image/Picasa/Album/Photocast"

class PhotocastRefreshController(ModalController):
    terra_type = \
            "Controller/Options/Folder/Image/Picasa/Album/Photocast/Refresh"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)

        model.callback_locked = self.start
        model.callback_unlocked = self.stop
        model.callback_refresh = self.update_text

        self.view = MessageView(parent, model.message_text)
        self.model.execute()

    def start(self):
        self.view.message(hide_cb=self.stop)
        self.model.callback_locked = None

    def stop(self):
        def cb():
            self.parent.back()
        self.view.hide(cb)

    def delete(self):
        self.view.delete()
        self.view = None
        self.model.callback_locked = None
        self.model.callback_unlocked = None

    def update_text(self):
        self.view.throbber.text_set(self.model.message_text)


class AlbumOptionsEditView(Modal):
    def __init__(self, parent, title, old_value, theme=None):
        Modal.__init__(self, parent.view, title, theme,
                       hborder=16, vborder=100)

        self.callback_ok_clicked = None
        self.callback_cancel_clicked = None
        self.callback_escape = None

        label = etk.Label("New value:")
        label.alignment_set(0.0, 1.0)
        label.show()

        self.entry = etk.Entry(text=old_value)
        self.entry.on_text_activated(self._on_ok_clicked)
        self.entry.show()

        vbox = etk.VBox()
        vbox.border_width_set(25)
        vbox.append(label, etk.VBox.START, etk.VBox.FILL, 0)
        vbox.append(self.entry, etk.VBox.START, etk.VBox.FILL, 10)
        vbox.show()

        self.modal_contents = PanelContentFrame(self.evas)
        self.modal_contents.frame.add(vbox)
        self.ok_button = self.modal_contents.button_add("OK")
        self.ok_button.on_clicked(self._on_button_clicked)
        self.cancel_button = self.modal_contents.button_add("  Cancel  ")
        self.cancel_button.on_clicked(self._on_button_clicked)

        self.modal_contents.handle_key_down = self.handle_key_down
        self.contents_set(self.modal_contents.object)

    def handle_key_down(self, ev):
        if ev.key == "Escape":
            if self.callback_escape:
                self.callback_escape()
            return False
        return True

    def _on_ok_clicked(self, *ignored):
        if self.callback_ok_clicked:
            self.callback_ok_clicked(self.entry.text)

    def _on_button_clicked(self, bt):
        if bt == self.ok_button:
            self._on_ok_clicked()
        elif bt == self.cancel_button:
            if self.callback_cancel_clicked:
                self.callback_cancel_clicked()

    def do_on_focus(self):
        self.modal_contents.object.focus = True

    @evas.decorators.del_callback
    def _destroy_contents(self):
        self.modal_contents.destroy()


class AlbumOptionsEditController(ModalController):
    terra_type = "Controller/Options/Folder/Image/Picasa/Album/Properties"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)
        self.model = model
        self.parent = parent
        self.view = AlbumOptionsEditView(parent.last_panel, model.title, \
                                                            model.old_value)

        self.view.callback_ok_clicked = self._on_ok_clicked
        self.view.callback_cancel_clicked = self.close
        self.view.callback_escape = self.close
        self.view.show()

    def close(self):
        def cb(*ignored):
            self.back()
            self.parent.back()
        self.view.hide(end_callback=cb)

    def _on_ok_clicked(self, new_title):
        def th_function():
            return self.model.update_value(new_title)

        def th_finished(exception, retval):
            def view_close():
                self.close()

            if not retval:
                self.view.throbber.text_set("ERROR!")
                ecore.timer_add(2, view_close)
                return
            self.close()

        self.view.hide()
        self.view = MessageView(self.parent.last_panel, "please wait")
        self.view.message()
        ThreadedFunction(th_finished, th_function).start()

    def delete(self):
        self.view.delete()
        self.view = None
        self.model = None

CheckListPanelController = manager.get_class("Controller/Settings/CheckedFolder")
CheckListPanel = manager.get_class("Widget/CheckListPanel")
CheckListRenderer = manager.get_class("Widget/CheckListRenderer")
PanelButtonWidget = manager.get_class("Widget/PanelButton")

class AlbumAccessItemRenderer(CheckListRenderer):
    def _is_selected(self, v):
        parent = v.parent
        return parent.current is not None and \
            parent.children[parent.current] is v


class AlbumAccessPanel(CheckListPanel):
    def __init__(self, main_window, title, elements, theme=None):
        header_text = \
                "Choose the the level of access for your album:"
        CheckListPanel.__init__(self, main_window, title, elements,
                                AlbumAccessItemRenderer,
                                theme=theme, header_text=header_text)
        self.callback_ok = None
        self._setup_buttons()

    def _setup_buttons(self):
        ok = PanelButtonWidget(self.evas, "OK",
                               clicked_callback=self._cb_ok_clicked,
                               parent=self)
        self._setup_button_box(right=ok)

    def _cb_ok_clicked(self, *ignored):
        if self.callback_ok is not None:
            self.callback_ok()


class AlbumAccessFolderController(CheckListPanelController):
    terra_type = "Controller/Options/Folder/Image/Picasa/Album/Properties/Access"
    def __init__(self, model, canvas, parent):
        CheckListPanelController.__init__(self, model, canvas, parent)
        def mark_selected(*args, **kargs):
            for i, m in enumerate(self.model.children):
                if m.selected:
                    self.model.current = i
                    break

            self.view.redraw_item(self.model.current)
            return False

        ecore.idler_add(mark_selected)

    def _setup_view(self):
        title = self.model.name
        self.view = AlbumAccessPanel(self.parent.window, title,\
                                            self.model.children)
        self.view.callback_clicked = self.cb_on_clicked
        self.view.callback_escape = self.back
        self.view.callback_ok = self.cb_on_ok

    def cb_on_clicked(self, view, index):
        old_index = self.model.current
        self.model.current = index

        if old_index is not None:
            self.view.redraw_item(old_index)
        self.view.redraw_item(index)

    def cb_on_ok(self):
        def th_function():
            new_access = self.model.children[self.model.current].name
            return self.model.update(new_access)

        def th_finished(exception, retval):
            self.view_wait.hide()
            self.view.hide()
            self.back()

        self.view_wait = MessageView(self.parent.last_panel, "please wait")
        self.view_wait.message()
        ThreadedFunction(th_finished, th_function).start()


class FullScreenUploadController(Controller):
    terra_type = "Controller/Options/Folder/Image/Fullscreen/Submenu/PicasaUpload"

    def __new__(cls, *args, **kargs):
        if not picasa_manager.is_logged():
            picasa_manager.login()

        if picasa_manager.is_logged():
            obj = Controller.__new__(ControllerOptionsFolder, *args, **kargs)
            obj.__init__(*args, **kargs)

        else:
            obj = Controller.__new__(FullScreenMessageController, *args, **kargs)
            kargs[message] = "User not logged in to Picasa"
            obj.__init__(*args, **kargs)

        return obj


class FullScreenMessageController(ModalController):
    def __init__(self, model, canvas, parent, message):
        ModalController.__init__(self, model, canvas, parent)
        self.view = ModalMessage(parent.last_panel, message)
        self.view.show()
        self.view.callback_clicked = self.stop

    def stop(self):
        self.view.hide()

    def delete(self):
        self.view.delete()
        self.view = None


class FullScreenUploadAlbumController(ModalController):
    terra_type = "Controller/Options/Folder/Image/Fullscreen/Submenu/PicasaUpload/Submenu"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)

        model.callback_locked = self.start
        model.callback_unlocked = self.stop
        model.callback_refresh = self._update_text
        model.callback_show_error = self._show_error

        self.parent = parent
        self.view = MessageView(parent.last_panel, "uploading")
        self.model.execute()

    def start(self):
        self.view.message(hide_cb=self.stop)
        self.model.callback_locked = None

    def stop(self):
        self.view.hide()

    def _update_text(self, text):
        self.view.throbber.text_set(text)

    def _show_error(self, error):
        self.view.hide()
        self.view.delete()
        self.view = ModalMessage(self.parent.last_panel, error)
        self.view.callback_clicked = self.stop

        self.view.show()

    def delete(self):
        self.view.delete()
        self.view = None
        self.model.callback_locked = None
        self.model.callback_unlocked = None
        self.model.callback_refresh = None

class FullScreenUploadAllController(ModalController):
    terra_type = "Controller/Options/Folder/Image/Fullscreen/Submenu/PicasaUploadAll"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)

        model.callback_locked = self.start
        model.callback_unlocked = self.stop
        model.callback_refresh = self.update_text
        model.callback_check_cancel = self._cancel_pressed
        model.callback_show_error = self._show_error

        self.parent = parent
        self.cancel = False

        self.view = ModalThrobber(parent.last_panel,\
                                "uploading<br> xx% done<br> 1 of 5 uploaded")
        self.view.callback_clicked = self._on_cancel
        self.model.execute()

    def _show_error(self, error):
        self.view.hide()
        self.view.delete()
        self.view = ModalMessage(self.parent.last_panel, error)
        self.view.callback_clicked = self.stop

        self.view.show()

    def _on_cancel(self):
        self.cancel = True

    def _cancel_pressed(self):
        return self.cancel

    def start(self):
        self.view.show()
        self.model.callback_locked = None

    def stop(self):
        self.view.hide()

    def update_text(self, text):
        self.view.throbber.text_set(text)

    def delete(self):
        self.view.delete()
        self.view = None
        self.model.callback_locked = None
        self.model.callback_unlocked = None
        self.model.callback_refresh = None

class FullScreenDeletePicOptionsController(ModalController):
    terra_type = "Controller/Options/Folder/Image/Fullscreen/Submenu/PicasaDelete"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)

        self.view = MessageView(parent.last_panel, "please wait")
        self.screen_controller = parent.screen_controller
        self.model.callback_delete_pic = self.delete_pic

        self.model.execute()

    def stop(self):
        def cb():
            self.parent.back()
        self.view.hide(cb)

    def start(self):
        self.view.message(hide_cb=self.stop)
        self.model.callback_locked = None

    def update_text(self, text):
        self.view.throbber.text_set(text)

    def delete(self):
        self.view.delete()
        self.view = None
        self.model.callback_locked = None
        self.model.callback_unlocked = None
        self.model.callback_refresh = None

    def delete_pic(self):

        def hide_cb():
            self.stop()

        def th_finished(exception, retval):
            if exception is not None:
                log.error("Exception while deleting image: %s" % exception)
                self.update_text("ERROR!")
                ecore.timer_add(2, hide_cb)
                return
            if not retval:
                log.error("Error while deleting image")
                self.update_text("ERROR!")
                ecore.timer_add(2, hide_cb)
                return

            if album_model.current > 0:
                self.screen_controller.prev()
            else:
                if album_model.current < album_model.size -1:
                    self.screen_controller.next()

            album_model.size -= 1
            album_model.prop["cntPhotos"] = str(album_model.size)

            album_model.children.remove(current_model)
            self.screen_controller._check_prev_next_visibility()

            album_model.parent.callback_update_list(current_model)

            self.stop()

        def th_func():
            return current_model.delete_model()

        album_model = self.screen_controller.model
        current_model = album_model.children[album_model.current]

        self.start()
        ThreadedFunction(th_finished, th_func).start()

BasicPanel = manager.get_class("Controller/BasicPanel")
BaseScrollableText = manager.get_class("Widget/ScrollableTextBlock")

class ScrollableTextBlock(PluginThemeMixin, BaseScrollableText):
    plugin = "picasa"
    group = "textblock_description"


class FullScreenImageInfoOptionsController(BasicPanel):
    terra_type = "Controller/Options/Folder/Image/Fullscreen/Submenu/PicasaImageInfo"

    def __init__(self, model, canvas, parent, theme=None,\
                                               edje_group="panel_info_picasa"):
        BasicPanel.__init__(self, model, canvas, parent)

        self.thumbnail = evas.FilledImage(canvas)

        self._body = PluginEdjeWidget(self.view.evas, edje_group,\
                                                    self.view, plugin="picasa")

        self.description = ScrollableTextBlock(self.view.evas, self.view)
        self._body.part_swallow("description", self.description)

        self.model = model
        self.image_data = self.model.get_image_model().image

        self.inner_contents_set(self._body)
        self.setup_information()

    def setup_information(self):
        title = self.image_data.media.title.text
        author = self.image_data.media.credit.text
        if self.image_data.exif.time is not None:
            date_taken = int(self.image_data.exif.time.text) / 1000
            date_taken = strftime("%b %d, %Y", gmtime(date_taken))
        else:
            date_taken = "N/A"

        self._body.part_text_set("title", title)
        self._body.part_text_set("author", "By " + author)
        self._body.part_text_set("date_taken", "Taken on " + date_taken )
        self._body.part_swallow("contents", self.thumbnail)

        text = ""
        if  self.image_data.summary is not None and\
                                    self.image_data.summary.text is not None:
            text = "Description:" + self.image_data.summary.text + "<br>"

        if self.image_data.media.keywords is not None and\
                                self.image_data.media.keywords.text is not None:
            text = text + "Tags:"
            text = text + self.image_data.media.keywords.text + "<br>"

        text = text + "Number of comments: " + self.image_data.commentCount.text + "<br>"

        if self.image_data.geo.Point.pos.text is not None:
            coord = self.image_data.geo.Point.pos.text.split(" ")
            lat = float(coord[0])
            long = float(coord[1])

            text = text + "Location: %.5f, %.5f" % (lat, long) + "<br>"

        dim = "Dimensions: %sx%s px" % (
                int(self.model.get_image_model().width),
                int(self.model.get_image_model().height)
            )
        text = text + dim

        self.description.text_set(text)

        try:
            thumbnail_path = self.model.get_image_model().thumb_path
            self.thumbnail.file_set(thumbnail_path)
            self._body.signal_emit("thumb,show", "")
        except Exception, e:
            self._body.signal_emit("thumb,hide", "")

    def delete(self):
        self._body.delete()
        self.thumbnail.delete()
        self.description.delete()
        BasicPanel.delete(self)

ControllerOptionsFolder = manager.get_class("Controller/Options/Folder")
class FullScreenCommentListOptionsController(ControllerOptionsFolder):
    terra_type = "Controller/Options/Folder/Image/Fullscreen/Submenu/PicasaCommentList"

    def __init__(self, model, canvas, parent):
        model.callback_finished = self.model_loaded
        ControllerOptionsFolder.__init__(self, model, canvas, parent)

    def model_loaded(self):
        if self.model.count == 0:
            msg_tit = "No comments for this photo"
        else:
            msg_tit = "%d comments for this photo" % self.model.count
        self.view.header_text_set(msg_tit)

    def _setup_view(self):
        ControllerOptionsFolder._setup_view(self)
        self.view.header_text_set("Loading comments...")

class FullScreenCommentOptionsController(BasicPanel):
    terra_type = "Controller/Options/Folder/Image/Fullscreen/Submenu/PicasaCommentList/Item"

    def __init__(self, model, canvas, parent, theme=None):
        BasicPanel.__init__(self, model, canvas, parent)
        self._body = PluginEdjeWidget(self.view.evas, "panel_comment_picasa",
                                     self.view, plugin="picasa")
        self.description = ScrollableTextBlock(self.view.evas, self.view)
        self._body.part_swallow("description", self.description)
        self.inner_contents_set(self._body)
        self.setup_information()

    def setup_information(self):
        model = self.model.screen_controller.model
        self._body.part_text_set("author", "By: %s" % self.model.prop["author"])

        date = parse_timestamp(self.model.prop["date"])
        self._body.part_text_set("date", "Date: %s" % \
                                            date.strftime("%b %d, %Y %I:%M%p"))

        comment_panel = self.model.prop["content"]
        comment_panel = comment_panel.replace("\n", "<br>")
        self.description.text_set(comment_panel)

    def delete(self):
        self._body.delete()
        self.description.delete()
        BasicPanel.delete(self)

class AddCommentView(Modal):
    def __init__(self, parent, title, old_value, theme=None):
        Modal.__init__(self, parent.view, title, theme,
                       hborder=16, vborder=50)
        self.callback_ok_clicked = None
        self.callback_cancel_clicked = None
        self.callback_escape = None

        label = etk.Label("Comment:")
        label.alignment_set(0.0, 1.0)
        label.show()

        self.entry = etk.TextView()

        self.entry.size_request_set(150,150)
        self.entry.show()


        vbox = etk.VBox()
        vbox.border_width_set(25)
        vbox.append(label, etk.VBox.START, etk.VBox.FILL, 0)
        vbox.append(self.entry, etk.VBox.START, etk.VBox.EXPAND, 0)
        vbox.show()

        self.modal_contents = PanelContentFrame(self.evas)
        self.modal_contents.frame.add(vbox)
        self.ok_button = self.modal_contents.button_add("OK")
        self.ok_button.on_clicked(self._on_button_clicked)
        self.cancel_button = self.modal_contents.button_add("  Cancel  ")
        self.cancel_button.on_clicked(self._on_button_clicked)

        self.modal_contents.handle_key_down = self.handle_key_down
        self.contents_set(self.modal_contents.object)

    def handle_key_down(self, ev):
        if ev.key == "Escape":
            if self.callback_escape:
                self.callback_escape()
            return False
        return True

    def _on_ok_clicked(self):
        text = self.entry.textblock_get().text_get(0)
        self.callback_ok_clicked(text)

    def _on_button_clicked(self, bt):
        if bt == self.ok_button:
            self._on_ok_clicked()
        elif bt == self.cancel_button:
            if self.callback_cancel_clicked:
                self.callback_cancel_clicked()

    def do_on_focus(self):
        self.modal_contents.object.focus = True

    @evas.decorators.del_callback
    def _destroy_contents(self):
        self.modal_contents.destroy()

class FullScreenAddCommentOptionsController(ModalController):
    terra_type = "Controller/Options/Folder/Image/Fullscreen/Submenu/PicasaAddComment"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)
        self.model = model
        self.parent = parent
        self.view = AddCommentView(parent.last_panel, model.title, None)

        self.view.callback_ok_clicked = self._on_ok_clicked
        self.view.callback_cancel_clicked = self.close
        self.view.callback_escape = self.close
        self.view.show()

    def close(self):
        def cb(*ignored):
            self.back()
            self.parent.back()
        self.view.hide(end_callback=cb)

    def _on_ok_clicked(self, comment):
        def th_function():
            return self.model.add_comment(comment)

        def th_finished(exception, retval):
            def view_close():
                self.close()

            if not retval:
                self.view.throbber.text_set("ERROR!")
                ecore.timer_add(2, view_close)
                return
            self.close()

        self.view.hide()
        self.view = MessageView(self.parent.last_panel, "please wait")
        self.view.message()
        ThreadedFunction(th_finished, th_function).start()

    def delete(self):
        self.view.delete()
        self.view = None
        self.model = None


class ModalThrobber(Modal, TerraObject):

    def __init__(self, parent, message,
                 has_cancel=True, theme=None, hborder=50, vborder=125):
        Modal.__init__(self, parent.view, "", parent.view.theme, hborder, vborder)
        self.has_cancel = has_cancel
        self._init_embed()
        self.message = message
        self.callback_escape = None
        self.callback_clicked = None

    def _init_embed(self):
        self.embed = etk.Embed(self.evas)

        self.vbox = etk.VBox()
        self.vbox.border_width = 25

        self.throbber = EtkThrobber("")
        self.throbber.show()
        self.throbber_align = etk.Alignment(0.5, 0.4, 0.0, 0.0,
                                            child=self.throbber)
        self.throbber_align.show()
        self.throbber.start()

        self.vbox.append(self.throbber_align, etk.VBox.START, etk.VBox.FILL, 0)

        if self.has_cancel:
            self.button = etk.Button(label="   Cancel   ")
            self.button.on_clicked(self.clicked)
            self.button.show()
            self.button_align = etk.Alignment(0.5, 0.5, 0.0, 0.0, child=self.button)
            self.button_align.show()

            self.vbox.append(self.button_align, etk.VBox.END, etk.VBox.FILL, 0)

        self.vbox.show()

        self.embed.on_key_down(self._key_down_cb)
        self.embed.on_key_up(self._key_up_cb)

        self.embed.add(self.vbox)
        self.embed.show()
        self.contents_set(self.embed.object)

    def show_message(self, error):
        self.label = etk.Label(error)
        self.label.show()
        self.label_align = etk.Alignment(0.5, 0.4, 0.0, 0.0,
                                            child=self.label)
        self.label_align.show()
        self.vbox.prepend(self.label_align, etk.VBox.START, etk.VBox.FILL, 0)

    def _message_set(self, value):
        self.throbber.text = value

    def _message_get(self):
        return self.throbber.text

    message = property(_message_get, _message_set)

    def clicked(self, *ignored):
        if self.callback_clicked:
            self.callback_clicked()
        self.button.hide()

    def _key_down_cb(self, o, ev):
        return self.handle_key_down(ev)

    def _key_up_cb(self, o, ev):
        return self.handle_key_up(ev)

    def handle_key_down(self, ev):
        if ev.key == "Escape":
            if self.callback_clicked:
                self.callback_clicked()
            return False
        return True

    def handle_key_up(self, ev):
        return True

    @evas.decorators.focus_in_callback
    def _focus_in(self):
        self.embed.object.focus = True
        self.do_on_focus()

    def do_on_focus(self):
        pass

    @evas.decorators.del_callback
    def _destroy_contents(self):
        self.embed.destroy()



class ModalMessage(Modal, TerraObject):
    terra_type = "Widget/Settings/ModalThrobber"

    def __init__(self, parent, message,
                 has_button=True, theme=None, hborder=50, vborder=125):
        Modal.__init__(self, parent.view, "", parent.view.theme, hborder, vborder)
        self.has_button = has_button
        self.message = message
        self.callback_clicked = None
        self._init_embed()

    def _init_embed(self):
        self.embed = etk.Embed(self.evas)

        self.vbox = etk.VBox()
        self.vbox.border_width = 25

        self.label = etk.Label(self.message)
        self.label.show()
        self.label_align = etk.Alignment(0.5, 0.4, 0.0, 0.0,
                                            child=self.label)
        self.label_align.show()
        self.vbox.append(self.label_align, etk.VBox.START, etk.VBox.FILL, 0)

        if self.has_button:
            self.button = etk.Button(label="   OK   ")
            self.button.on_clicked(self.clicked)
            self.button.show()
            self.button_align = etk.Alignment(0.5, 0.5, 0.0, 0.0, child=self.button)
            self.button_align.show()

            self.vbox.append(self.button_align, etk.VBox.END, etk.VBox.FILL, 0)

        self.vbox.show()

        self.embed.add(self.vbox)
        self.embed.show()
        self.contents_set(self.embed.object)

    def clicked(self, *ignored):
        if self.callback_clicked:
            self.callback_clicked()

    @evas.decorators.focus_in_callback
    def _focus_in(self):
        self.embed.object.focus = True
        self.do_on_focus()

    def do_on_focus(self):
        pass

    @evas.decorators.del_callback
    def _destroy_contents(self):
        self.embed.destroy()
