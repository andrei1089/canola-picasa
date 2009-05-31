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
import logging

from terra.core.manager import Manager
from terra.core.threaded_func import ThreadedFunction

from manager import PicasaManager

manager = Manager()
picasa_manager = PicasaManager()

network = manager.get_status_notifier("Network")

ModalController = manager.get_class("Controller/Modal")
PanelContentModal = manager.get_class("Widget/Settings/PanelContentModal")
MixedListController = manager.get_class("Controller/Settings/Folder/MixedList")

log = logging.getLogger("plugins.canola-picasa.options")

###########################################################
#Settings
###########################################################

class OptionsController(MixedListController):
    terra_type = "Controller/Settings/Folder/InternetMedia/Picasa"


class UserPassController(ModalController):
    terra_type = "Controller/Settings/Folder/InternetMedia/Picasa/UserPass"

    def __init__(self, model, canvas, parent):

        ModalController.__init__(self, model, canvas, parent)
        self.parent_controller = parent
        self.model = model
        print "!!!!parent = " + str(parent)
        print "!!!dir parent = " + str(dir(parent))
        print "!!parent.parent = " + str(parent.parent)
        self.view = UsernamePasswordModal(parent, "Login to Picasa",
                                          parent.view.theme,
                                          vborder=50)

        picasa_manager.reload_prefs()
        self.view.username = picasa_manager.getUser()
        self.view.password = picasa_manager.getPassword()

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

        picasa_manager.setUser(self.view.username)
        picasa_manager.setPassword(self.view.password)
        def refresh(session):
            session.login()

        def refresh_finished(exception, retval):
            def cb_close(*ignored):
                self.close()
                self.parent.killall()

            if picasa_manager.is_logged():
                self.model.title = "Logged as %s" % picasa_manager.getUser()
                self.view.message("Login successful")
                ecore.timer_add(1.5, cb_close)

            else:
                self.view.message("Login error: %s" % picasa_manager.get_login_error() )
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
            #self.parent_controller.view.list.redraw_queue()
            self.back()
        self.view.hide(end_callback=cb)

    def _on_ok_clicked(self):
        def cb_close(*ignored):
            self.close()

        print "ok clicked"

        if not self.view.name:
            self.view.message_wait("Missing name")
            ecore.timer_add(2, cb_close)


    def delete(self):
        self.view.delete()
        self.view = None
        self.model = None

