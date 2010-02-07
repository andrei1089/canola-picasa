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

import logging
import ecore

import gdata.photos.service
import gdata.media
import gdata.geo
import gdata.service
import os
import thumbnailer
import math

import dbus
try:
    from e_dbus import DBusEcoreMainLoop
    DBusEcoreMainLoop(set_as_default=True)
except Exception:
    import dbus.ecore

from gdata.photos.service import GooglePhotosException
from terra.core.singleton import Singleton
from terra.core.plugin_prefs import PluginPrefs

log = logging.getLogger("plugins.canola-picasa.manager")

#because there is no integration between Ecore and Glib loops we use
#a different process to get data from GPS
class GpsManager(Singleton):
    def __init__(self):
        Singleton.__init__(self)
        #TODO: really check if GPS is available
        self.gps_available = False

        self.lat = None
        self.long = None
        self.radius = 10
        self.callback_location_updated = None
        self.remote_object = None

    def start(self):
        log.info("Starting GPS Daemon")
        bus = dbus.SessionBus()

        try:
            self.remote_object = bus.get_object("org.maemo.canolapicasa.GPSService",
                                           "/GPSObject")
            self.gps_available = self.remote_object.StartGPS(dbus_interface="org.maemo.canolapicasa.Interface")
            self.remote_object.connect_to_signal("EmitNewCoords", self.update_coords, dbus_interface="org.maemo.canolapicasa.Interface")
        except dbus.DBusException:
            log.error("Error while trying to start GPS daemon")
            self.gps_available = False
        return self.gps_available

    def stop(self):
        if not self.gps_available:
            return
        log.info("Stopping GPS Daemon")
        try:
            self.remote_object.StopGPS(dbus_interface="org.maemo.canolapicasa.Interface")
        except dbus.DBusException, e:
            log.error("Error while trying to stop GPS daemon: %s" % e)

    def update_coords(self):
        coords = self.remote_object.GetNewCoords(dbus_interface="org.maemo.canolapicasa.Interface")
        self.lat, self.long = coords
        log.info("New coords available: %f, %f" % (self.lat, self.long))
        if self.callback_location_updated:
            self.callback_location_updated()

class PicasaManager(Singleton):
    def __init__(self):
        Singleton.__init__(self)
        self.gd_client = gdata.photos.service.PhotosService()
        self.gd_client.email = ''
        self.gd_client.password = ''
        self.gd_client.source = 'Picasa plugin for Canola'
        self.logged = False
        self.login_error = ''
        self._user = ''
        self._password = ''
        self.albums =''
        self.thumbs_path = ''
        self.outside_terra = False;

        #used to save the list of current downloading thumbs to avoid multiple
        #downloads for the same file
        self.thumbs_in_progress = {};

        try:
            self.prefs = PluginPrefs("picasa")
        except:
            print "running outside canola"
            self.outside_terra = True;

    def load_thumbler(self):
        try:
            self.thumbler = thumbnailer.CanolaThumbnailer()
        except RuntimeError, e:
            log.error(e)
            self.thumbler = None

    def unload_thumbler(self):
        if self.thumbler:
            self.thumbler.stop()
        self.thumbler = None

    def reload_prefs(self):
        self.user = self.get_preference("username", "")
        self.password = self.get_preference("password", "")

    def get_preference(self, name, default=None):
        return self.prefs.get(name, default)

    def get_thumbs_path(self):
        if not self.thumbs_path:
            try:
                self.thumbs_path = self.prefs["thumbs_path"]
            except KeyError:
                try:
                    download_path = PluginPrefs("settings")["download_path"]
                except KeyError:
                    download_path = os.path.join(os.path.expanduser("~"), ".canola")

                self.thumbs_path = os.path.join(download_path, "picasa", "thumbnails")
                self.set_preference("thumbs_path", self.thumbs_path)

        if not os.path.exists(self.thumbs_path):
            os.makedirs(self.thumbs_path)

        return self.thumbs_path

    def set_preference(self, name, value):
        self.prefs[name] = value
        self.prefs.save()

    def getPassword(self):
        return self._password

    def setPassword(self, password):
        self._password = self.gd_client.password = password
        if not self.outside_terra:
            self.set_preference("password", password)

    password = property(getPassword, setPassword)

    def getUser(self):
        return self._user

    def setUser(self, email):
        self._user = self.gd_client.email = email
        if not self.outside_terra:
            self.set_preference("username", email)

    user = property(getUser, setUser)

    def login(self):
        if not self.outside_terra:
            self.reload_prefs()
        try:
            self.gd_client.ProgrammaticLogin()
            self.logged = True
            self.albums = None
        except gdata.service.Error, error:
            log.error("Could not login to Picasa, exception: %s" % error)
            self.login_error = error
            self.logged = False

    def is_logged(self):
        return self.logged

    def get_user_albums(self):
        if not self.albums:
            self.refresh_user_albums(self.user)
        return 	self.albums

    def get_community_albums(self, user):
        return self.gd_client.GetUserFeed(user=user)

    def refresh_user_albums(self, user):
        self.albums = self.gd_client.GetUserFeed(user=user)

    def create_album(self, title, description=None):
        try:
            return self.gd_client.InsertAlbum(title, description)
        except:
            return None

    def _get_album_from_id(self, id):
        albums = self.get_user_albums()
        for i in albums.entry:
            if i.gphoto_id.text == id:
                return i
        return None

    def delete_album(self, id):
        album = self._get_album_from_id(id)
        if album is not None:
            try:
                ret = self.gd_client.Delete(album)
                self.refresh_user_albums(self.user)
                return ret
            except:
                return False
        return False

    def delete_photo(self, photo):
        try:
            return self.gd_client.Delete(photo)
        except:
            return False

    def get_photos_from_album(self, album_id, user = None) :
        if not user:
            user = self.user
        return \
          self.gd_client.GetFeed('/data/feed/api/user/%s/albumid/%s?kind=photo'\
                                                        % (user , album_id) )
    def get_login_error(self):
        return self.login_error

    def update_title(self, album_id, new_title):
        album = self._get_album_from_id(album_id)
        if new_title == album.title.text:
            return True
        album.title.text = new_title

        try:
            updated_album = self.gd_client.Put(album, album.GetEditLink().href,
                    converter=gdata.photos.AlbumEntryFromString)
        except:
            log.error("Error while updating album's title")
            return False

        self.refresh_user_albums(self.user)
        return True

    def update_desc(self, album_id, new_desc):
        album = self._get_album_from_id(album_id)
        if new_desc == album.summary.text:
            return True
        album.summary.text = new_desc

        try:
            updated_album = self.gd_client.Put(album, album.GetEditLink().href,
                    converter=gdata.photos.AlbumEntryFromString)
        except:
            log.error("Error while updating album's description")
            return False

        self.refresh_user_albums(self.user)
        return True

    def update_access(self, album_id, new_access):
        album = self._get_album_from_id(album_id)
        if new_access == album.access.text:
            return True
        album.access.text = new_access

        try:
            updated_album = self.gd_client.Put(album, album.GetEditLink().href,
                    converter=gdata.photos.AlbumEntryFromString)
        except:
            log.error("Error while updating album's description")
            return False

        self.refresh_user_albums(self.user)
        return True

    def upload_picture(self, path, album, summary=None):
        album_url = '/data/feed/api/user/default/albumid/%s' % album
        if summary is None:
            summary = os.path.basename(path)
        try:
            self.gd_client.InsertPhotoSimple(album_url, summary, \
                summary, path, content_type='image/jpeg')
        except GooglePhotosException, error:
            log.error("upload error %s" % error)
            return (False, error)
        return (True, None)

    def _get_image_prop(self, image):
        image_id = image.gphoto_id.text
        album_id = image.albumid.text

        link = image.link[0].href
        link = link[link.find("/user/")+6:]
        user = link[:link.find("/albumid/")]
        return (user, album_id, image_id)


    def get_comments_for_image(self, image):
        user, album_id, image_id = self._get_image_prop(image)
        url = "http://picasaweb.google.com/data/feed/api/user/%s/albumid/%s/photoid/%s?kind=comment" % ( user, album_id, image_id)

        feed = self.gd_client.GetFeed(url)
        list = []
        for i in feed.entry:
            c = {}
            c["author"] = i.author[0].name.text
            c["content"] = i.content.text
            c["date"] = i.published.text
            c["title"] = c["content"][:40]
            list.append(c)
        return list

    def add_comment(self, image, comment):
        try:
            self.gd_client.InsertComment(image, comment)
        except:
            return False
        return True

if __name__ == "__main__":
    p=PicasaManager()
    p.user = 'xxxxxxx'
    p.password = 'xxxxxxx'
    p.login()
    print p.is_logged()

    al=[]
    p.refresh_user_albums('canolapicasa')
    x = p.get_user_albums()
    for i in x.entry:
        al.append(i)

    x= p.get_user_albums()
    z=[]
    for i in x.entry:
        print i.title.text
        z.append(i.gphoto_id.text)

        zz = i

    y=p.get_photos_from_album(zz.gphoto_id.text)
    for i in y.entry:
    	zzz=i

