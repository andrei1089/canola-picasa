import gdata.photos.service
import gdata.media
import gdata.geo
import gdata.service
import os


class PicasaManager:
    def __init__(self):
        self.gd_client = gdata.photos.service.PhotosService()
        self.gd_client.email = ''
        self.gd_client.password = ''
        self.gd_client.source = 'Picasa plugin for Canola'
        self.logged = False
        self.login_error = ''
        self.user = '' 
        self.password = ''
        self.albums =''
        self.outside_terra = False;
        try:
            from terra.core.plugin_prefs import PluginPrefs
            self.prefs = PluginPrefs("picasa")
        except:
            print "running outside canola"
            self.outside_terra = True;


    def reload_prefs(self):
        self.setUser( self.get_preference("username", ""))
        self.setPassword ( self.get_preference("password", "") )

    def get_preference(self, name, default=None):
        return self.prefs.get(name, default)

    def get_thumbs_path(self):
        try:
            path = self.prefs["thumbs_path"]
        except KeyError:
            path = os.path.join( os.path.expanduser("~"), ".canola", "picasa", "thumbs")
            self.prefs["thumbs_path"] = path
            self.prefs.save()
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def set_preference(self, name, value):
        self.prefs[name] = value
        self.prefs.save()

    def setPassword(self, password):
        self.password = self.gd_client.password = password
        if not self.outside_terra:
            self.set_preference("password", password)

    def setUser(self, email):
        self.user = self.gd_client.email = email
        if not self.outside_terra:
            self.set_preference("username", email)

    def getUser(self):
        return self.user

    def getPassword(self):
        return self.password

    def login(self):
        if not self.outside_terra:
            self.reload_prefs()
        try:
            self.gd_client.ProgrammaticLogin()
            self.logged = True 
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

    def refresh_user_albums(self, user):
        self.albums = self.gd_client.GetUserFeed(user=user)

    def create_album(self, title, description):
        return self.gd_client.InsertAlbum(title, description)

    def delete_album(self, id):
        albums = self.get_user_albums()
        album = None
        for i in albums:
            if i.gphoto_id.text == id:
                album = i
                break
        if album is None:
            return False
        else:
            return self.gd_client.Delete(album)


    def get_photos_from_album(self, album):
        return self.gd_client.GetFeed('/data/feed/api/user/%s/albumid/%s?kind=photo' % (album.user.text, album.gphoto_id.text) )

    def get_login_error(self):
        return self.login_error

#p=PicasaManager()
#p.setUser('canolapicasa')
#p.setPassword('1234abcd')
#p.login()
#p.is_logged()

#al=[]
#p.refresh_user_albums('canolapicasa')
#x = p.get_user_albums()
#for i in x.entry:
#    al.append(i)

#x= p.get_user_albums()
#z=[]
#for i in x.entry:
#	print i.title.text
#	z.append(i.gphoto_id.text)

#y=p.get_photos_from_album(zz)

#for i in y.entry:
#	zz=i;
#a=p.get_photos_from_album(zz)

