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
import gobject

import ctypes as C
from types import MethodType

from gdata.photos.service import GooglePhotosException
from terra.core.singleton import Singleton
from terra.core.plugin_prefs import PluginPrefs

log = logging.getLogger("plugins.canola-picasa.manager")

class GpsManager(Singleton):
    def __init__(self):
        Singleton.__init__(self)

        self.gps_available = True
        try:
            import liblocation
        except:
            self.gps_available = False

        self.lat = None
        self.long = None
        self.callback_location_updated = None
        self.stop_on_exit = False

    def notify_gps_update(self, gps_dev):
        # Note: not all structure elements are used here,
        # but they are all made available to python.
        # Accessing the rest is left as an exercise.

        # struct() gives access to the underlying ctypes data.
        # ctypes magically converts things for us.
        gps_struct = gps_dev.struct()
        print 'online', gps_struct.online
        print 'status', gps_struct.status

        # Not sure if fix can ever be None, but check just in case.
        fix = gps_struct.fix
        if fix:
            print 'mode', fix.mode
            print 'gps time', fix.time
            print 'latitude', fix.latitude
            print 'longitude', fix.longitude

            self.lat = fix.latitude
            self.long = fix.longitude
            if not math.isnan(fix.latitude):
                if self.callback_location_updated:
                    self.callback_location_updated()

        print 'satellites_in_view', gps_struct.satellites_in_view
        print 'satellites_in_use', gps_struct.satellites_in_use

        # satellites is an iterator.
        for sv in gps_struct.satellites:
            print 'prn', sv.prn
            print 'elevation', sv.elevation
            print 'azimuth', sv.azimuth
            print 'signal_strength', sv.signal_strength
            print 'in_use', sv.in_use
        print

    def check_gps(self):
        print "check gps coords"
        gps_struct = self.gps.struct()
        fix = gps_struct.fix
        if fix:
            print 'mode', fix.mode
            print 'gps time', fix.time
            print 'latitude', fix.latitude
            print 'longitude', fix.longitude

            self.lat = fix.latitude
            self.long = fix.longitude
            if self.callback_location_updated:
                self.callback_location_updated()
        else:
            print "no coords yet, trying again in 5 sec"
        ecore.timer_add(5, self.check_gps)

    def start(self):
        # required to be initialized when using gpsd_control stuff
        gobject.threads_init()

        # create a gps device object (which is a full pythonic gobject)
        gps = liblocation.gps_device_get_new()

        # connect its gobject 'changed' signal to our callback function
        gps.connect('changed', self.notify_gps_update)

        # create a gpsd_control object (which is a full pythonic gobject)
        self.gpsd_control = liblocation.gpsd_control_get_default()

        # are we the first one to grab gpsd?  If so, we can and must
        # start it running.  If we didn't grab it first, then we cannot
        # control it.
        if self.gpsd_control.struct().can_control:
            liblocation.gpsd_control_start(self.gpsd_control)
            self.stop_on_exit = True

        self.gps = gps
        ecore.timer_add(5, self.check_gps)
        print "gps started"

    def stop(self):
        if self.stop_on_exit and self.gpsd_control.struct().can_control:
            liblocation.gpsd_control_stop(self.gpsd_control)

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
    p.user = 'canolapicasa'
    p.password = '1234abcd'
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

