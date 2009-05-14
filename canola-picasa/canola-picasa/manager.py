import gdata.photos.service
import gdata.media
import gdata.geo
import gdata.service

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

    def reload_prefs(self):
        try:
            from terra.core.plugin_prefs import PluginPrefs
            self.prefs = PluginPrefs("picasa")
            self.setUser( self.get_preference("username", ""))
            self.setPassword ( self.get_preference("password", "") )
        except:
            print "running outside canola"

    def get_preference(self, name, default=None):
        return self.prefs.get(name, default)

    def set_preference(self, name, value):
        self.prefs[name] = value
        self.prefs.save()

    def setPassword(self, password):
        self.password = self.gd_client.password = password
        self.set_preference("password", password)

    def setUser(self, email):
        self.user = self.gd_client.email = email
        self.set_preference("username", email)

    def getUser(self):
        return self.user

    def getPassword(self):
        return self.password

    def login(self):
        self.reload_prefs()
        try:
            self.gd_client.ProgrammaticLogin()
            self.logged = True 
        except gdata.service.BadAuthentication, X: 
            print "auth failed, reason:", X
            self.login_error = X.message
            self.logged = False 
        except: 
            print "auth failed"
            self.logged = False
            self.login_error = "unknown error"

    def is_logged(self):
        return self.logged
	
    def get_user_albums(self):
        if not self.albums:
            self.refresh_user_albums(self.user)
        return 	self.albums

    def refresh_user_albums(self, user):
        print "user222=", user
        self.albums = self.gd_client.GetUserFeed(user=user)

    def get_photos_from_album(self, album):
        return self.gd_client.GetFeed('/data/feed/api/user/%s/albumid/%s?kind=photo' % (album.user.text, album.gphoto_id.text) )

    def get_login_error(self):
        return self.login_error

#p=PicasaManager()
#p.setUser('canolapicasa')
#p.setPassword('1234abcd')
#p.login()
#p.is_logged()

#x= p.get_user_albums()
#z=[]
#for i in x.entry:
#	print i.title.text
#	z.append(i.gphoto_id.text)

#y=p.get_photos_from_album(zz)

#for i in y.entry:
#	zz=i;
#a=p.get_photos_from_album(zz)

