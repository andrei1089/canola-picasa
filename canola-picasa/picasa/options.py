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

from terra.core.manager import Manager
from terra.core.threaded_func import ThreadedFunction
from terra.ui.modal import Modal
from terra.ui.throbber import EtkThrobber
from terra.ui.panel import PanelContentFrame

from manager import PicasaManager

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
                self.view.message("Login error: %s" % \
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

        if not self.view.name:
            self.view.message_wait("Missing name")
            ecore.timer_add(2, cb_close)
            return


        AlbumModelFolder = self.parent.screen_controller.model
        status = AlbumModelFolder.create_album(self.view.name, \
                                                    self.view.description)
        if not status:
            self.view.message_wait("Failed to add new album")
            ecore.timer_add(2, cb_close)
            return
        self.close();


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
        self.model.update_value(new_title)
        self.close()

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
        new_access = self.model.children[self.model.current].name
        self.model.update(new_access)
        self.back()
