class ListAlbums(ModelFolder):
    terra_type = "Model/Folder/Task/Image/Picasa/ListAlbums"

    def __init__(self, parent):
        ModelFolder.__init__(self, "List albums", parent)
        print "listalbums - init finished"

    def do_load(self):
        picasa_manager.setUser('canolapicasa')
        picasa_manager.setPassword('1234abcd')
        #TODO: Threaded login, check if login successful

        picasa_manager.login() 
        print "is_logged", picasa_manager.is_logged()
        print "user_name=", picasa_manager.getUser()

        albums = picasa_manager.get_user_albums()
        
        for i in albums.entry:
            print "list picture : ", i.title.text
            ListPictures(i.title.text, self, i)

class Picture(ModelFolder):
    terra_type="Model/Folder/Task/Image/Picasa"
    def __init__(self, name, parent, picture):
        ModelFolder.__init__(self, name, parent)
        self.picture = picture
 class ListPictures(ModelFolder):
    terra_type = "Model/Folder/Task/Image/Picasa"

    def __init__(self,name, parent, album):
        ModelFolder.__init__(self,name, parent)	
        self.album = album
        print "getting photos"
        self.pictures = picasa_manager.get_photos_from_album(album)

    def do_load(self):
        for i in self.pictures.entry:
            Picture(i.title.text, self, i)



