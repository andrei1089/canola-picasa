#!/usr/bin/env python

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

import gobject

import dbus
import dbus.service
import dbus.mainloop.glib

gps_available = True
try:
    import location
    maemo5 = True
except:
    maemo5 = False

if not maemo5:
    try:
        import liblocation
    except:
        gps_available = False

class GPSMaemo():
    lat = 0
    long = 0
    callback = None

    def set_callback(self, callback):
        self.callback = callback

    def get_coords(self):
        return self.lat, self.long

class GPSMaemo4(GPSMaemo):
    def __init__(self):
        gps = liblocation.gps_device_get_new()
        gps.connect('changed', self.on_changed)

        # create a gpsd_control object (which is a full pythonic gobject)
        self.gpsd_control = liblocation.gpsd_control_get_default()
        self.stop_on_exit = False

    def start_location(self):
        # are we the first one to grab gpsd?  If so, we can and must
        # start it running.  If we didn't grab it first, then we cannot
        # control it.
        if gpsd_control.struct().can_control:
            liblocation.gpsd_control_start(self.gpsd_control)
            self.stop_on_exit = True

    def stop_location(self):
        if self.stop_on_exit:
            liblocation.gpsd_control_stop(self.gpsd_control)

    def on_changed(self, gps_dev):
        gps_struct = gps_dev.struct()
        fix = gps_struct.fix
        if fix:
            print fix.mode
            if fix.mode >= 2:
                self.lat = fix.latitude
                self.long = fix.longitude
                print "lat = %f, long = %f" % (self.lat, self.long)
                if self.callback is not None:
                    self.callback()

class GPSMaemo5(GPSMaemo):
    def __init__(self):
        self.control = location.GPSDControl.get_default()
        self.device = location.GPSDevice()
        self.control.set_properties(preferred_method=location.METHOD_USER_SELECTED,
                               preferred_interval=location.INTERVAL_DEFAULT)

        self.device.connect("changed", self.on_changed, self.control)

    def on_changed(self, device, data):
        if not device:
            return
        if device.fix:
            print device.fix
            if device.fix[0] >= 2 and device.fix[1] & location.GPS_DEVICE_LATLONG_SET:
                print "lat = %f, long = %f" % device.fix[4:6]
                self.lat, self.long = device.fix[4:6]
                if self.callback is not None:
                    self.callback()

    def start_location(self):
        self.control.start()

    def stop_location(self):
        self.control.stop()

class GPSObject(dbus.service.Object):
    GPS = None

    @dbus.service.method("org.maemo.canolapicasa.Interface",
                         in_signature='', out_signature='b')
    def StartGPS(self):
        if not gps_available:
            return False
        if maemo5:
            self.GPS = GPSMaemo5()
        else:
            self.GPS = GPSMaemo4()

        self.GPS.set_callback(self.EmitNewCoords)
    	self.GPS.start_location()
        return True

    @dbus.service.signal("org.maemo.canolapicasa.Interface")
    def EmitNewCoords(self):
        pass

    @dbus.service.method("org.maemo.canolapicasa.Interface",
                         in_signature='', out_signature='ad')
    def GetNewCoords(self):
        return self.GPS.get_coords()

    @dbus.service.method("org.maemo.canolapicasa.Interface",
                         in_signature='', out_signature='')
    def StopGPS(self):
	self.GPS.stop_location()
        mainloop.quit()

if __name__ == '__main__':
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    session_bus = dbus.SessionBus()
    name = dbus.service.BusName("org.maemo.canolapicasa.GPSService", session_bus)
    object = GPSObject(session_bus, '/GPSObject')

    mainloop = gobject.MainLoop()
    mainloop.run()
