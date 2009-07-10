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

import gdata.photos.service
import gdata.media
import gdata.geo
import gdata.service
import os
from terra.core.singleton import Singleton

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
        self.outside_terra = False;
        try:
            from terra.core.plugin_prefs import PluginPrefs
            self.prefs = PluginPrefs("picasa")
        except:
            print "running outside canola"
            self.outside_terra = True;


    def reload_prefs(self):
        self.user = self.get_preference("username", "")
        self.password = self.get_preference("password", "")

    def get_preference(self, name, default=None):
        return self.prefs.get(name, default)

    def get_thumbs_path(self):
        try:
            path = self.prefs["thumbs_path"]
        except KeyError:
            path = os.path.join( os.path.expanduser("~"), ".canola", \
                                                    "picasa", "thumbs")
            self.prefs["thumbs_path"] = path
            self.prefs.save()
        if not os.path.exists(path):
            os.makedirs(path)
        return path

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
        except gdata.service.BadAuthentication, X:
            self.login_error = X.message
            self.logged = False
        except:
            self.logged = False
            self.login_error = "unknown error"

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
        albums = self.get_user_albums()
        album = self._get_album_from_id(id)
        if album is not None:
            ret = self.gd_client.Delete(album)
            self.refresh_user_albums(self.user)
            return ret
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
        except:
            return False
        return True

    def get_comments_for_image(self, image):
        image_id = image.gphoto_id.text
        album_id = image.albumid.text
        
        link = image.link[0].href
        link = link[link.find("/user/")+6:]
        user = link[:link.find("/albumid/")]

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

