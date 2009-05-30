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

import ecore
import logging

from terra.core.manager import Manager
from terra.core.threaded_func import ThreadedFunction

from manager import PicasaManager

manager = Manager()
picasa_manager = PicasaManager()

network = manager.get_status_notifier("Network")

ModalController = manager.get_class("Controller/Modal")
UsernamePasswordModal = manager.get_class("Widget/Settings/UsernamePasswordModal")
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


class PicasaAddAlbumOptionController(ModalController):
    terra_type = "Controller/Options/Folder/Image/Picasa/Album/AddAlbum"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)

        self.parent_controller = parent
        self.model = model
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

