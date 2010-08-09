#
# This file is part of Canola
# Copyright (C) 2007-2009 Instituto Nokia de Tecnologia
# Contact: Renato Chencarek <renato.chencarek@openbossa.org>
#          Eduardo Lima (Etrunko) <eduardo.lima@openbossa.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#

import os
import ecore
import struct
import select
import logging
from signal import SIGKILL

STRFMT = "liiii1024s"
REPLY_MSGLEN = struct.calcsize(STRFMT)

log = logging.getLogger("canola.plugins.thumbnailer")

class CanolaThumbnailer(object):
    """Client class to access the thumbnail server for canola
       thumb size generation.

    """

    def __init__(self):
        self.requests = {}
        self.current = None

        try:
            reply_r, reply_w = os.pipe()
            request_r, request_w = os.pipe()

            def check_exec(file):
                for d in os.getenv('PATH').split(':'):
                    name = os.path.join(d, file)
                    if os.path.isfile(name) and \
                            os.access(name, os.X_OK | os.R_OK):
                        return True
                return False

            if not check_exec("canola-thumbnailer"):
                raise RuntimeError, "thumbnailer not found!"

            pid = os.fork()

            if pid == 0:
                os.close(reply_r)
                os.close(request_w)
                os.execlp("canola-thumbnailer", "canola-thumbnailer",
                          str(request_r), str(reply_w))
                return

            self.child = pid
            os.close(reply_w)
            os.close(request_r)
        except OSError:
            log.error("error forking thumbnailer process")

        self.pipe = PipeWrapper(reply_r, request_w)
        self.sock_id = ecore.fd_handler_add(reply_r,
                                            ecore.ECORE_FD_READ,
                                            self._process_socket)

    def _request_send(self, id, path, size, a, w, h):
        log.debug("Thumbnailing request added for : %s", path)
        msg = struct.pack(STRFMT, id, size, a, w, h, path)
        try:
            self.pipe.send(msg)
        except RuntimeError:
            log.error("error sending request")
            self.stop()

    def _request_next(self):
        if self.current or not self.requests:
            return

        self.current = self.requests.popitem()
        id, (path, size, a, w, h, l) = self.current
        self._request_send(id, path, size, a, w, h)

    def request_add(self, path, size, a, w, h, callback):
        id = hash((path, w, h))

        l = self.requests.setdefault(id, (path, size, a, w, h, []))
        l[5].append(callback)
        self._request_next()
        return id

    def request_cancel(self, id, cb):
        if not self.requests:
            return
        try:
            l = self.requests[id][4]
            l.remove(cb)
            if not l:
                self.requests.pop(id)
        except:
            pass

    def request_cancel_all(self):
        self.requests = {}

    def _process_socket(self, *ignored):
        try:
            msg = self.pipe.receive(REPLY_MSGLEN)
            (id, size, a, w, h, dest_path) = struct.unpack(STRFMT, msg)
            dest_path = dest_path[:dest_path.find('\x00')]
        except RuntimeError:
            self.delete()
            return False

        if id != self.current[0]:
            self.current = None
            self._request_next()
            return

        src_path, size, a, d_w, d_h, l = self.current[1]

        for cb in l:
            cb(src_path, dest_path, w, h)

        self.current = None
        self._request_next()

        return True

    def delete(self):
        self.pipe.close()
        self.sock_id.delete()
        # kill child
        os.kill(self.child, SIGKILL)
        os.wait()

    def stop(self):
        self.delete()


class PipeWrapper:
    def __init__(self, fd_r, fd_w):
        self.fd_r = fd_r
        self.fd_w = fd_w
        self.closed = False

    def send(self, msg):
        if self.closed:
            log.debug("Trying to send msg on a closed file descriptor")
            return

        totalsent = 0
        while totalsent < len(msg):
            sent = os.write(self.fd_w, msg[totalsent:])
            if sent == 0:
                raise RuntimeError, \
                    "pipe connection broken"
            totalsent = totalsent + sent

    def receive(self, msg_len):
        if self.closed:
            log.debug("Trying to receive msg on a closed file descriptor")
            return

        msg = ''
        while len(msg) < msg_len:
            chunk = os.read(self.fd_r, msg_len - len(msg))
            if chunk == '':
                raise RuntimeError, \
                    "pipe connection broken"
            msg = msg + chunk
        return msg

    def close(self):
        self.closed = True
        os.close(self.fd_r)
        os.close(self.fd_w)

