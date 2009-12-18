#
# Copyright (c) 2007-2009, REvolution Computing, Inc.
#
# NetWorkSpaces is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307
# USA
#

"""Implementation of NWS server startup as an interpreter-local thread."""

import threading, time
from twisted.internet import reactor
from nwss.server import NwsService

__all__ = ['NwsLocalServerException', 'NwsLocalServer']

class NwsLocalServerException(Exception):
    """Exception thrown if an error occurs while starting the local server."""
    pass

class NwsLocalServer(threading.Thread):
    """Utility to start the NWS server as a thread within a Python
    interpreter."""

    def __init__(self, port=0, interface='', daemon=True,
                 name='NwsLocalServer', **kw):
        threading.Thread.__init__(self, name=name, **kw)
        self.__desired_port = port
        self.__port = None
        self.__interface = interface
        self.__started = False
        self.__condition = threading.Condition()
        self.setDaemon(daemon)
        self.start()

    def get_port(self):
        """Get the actual port number to which we bound."""
        return self.__port._realPortNumber  #pylint: disable-msg=W0212
    port = property(get_port)

    def shutdown(self, timeout=None):
        """Request the shutdown of the server, waiting at most 'timeout'
        seconds for the server thread to stop."""
        reactor.callFromThread(reactor.stop) #pylint: disable-msg=E1101
        self.join(timeout=timeout)

    def wait_until_started(self, timeout=30):
        """Wait for the server thread to finish initializing.  Wait for at most
        'timeout' seconds for the server to start, throwing
        NwsLocalServerException if it has not started by the time the timer
        expires."""

        start_time = time.time()
        timeout_remain = timeout

        self.__condition.acquire()
        try:
            while not self.__started:
                self.__condition.wait(timeout=timeout_remain)
                if timeout is not None:
                    timeout_remain = start_time + timeout - time.time()
                    if timeout_remain <= 0:
                        break

            if not self.__started:
                raise NwsLocalServerException(
                        'local server timeout expired: %d' % timeout)
        finally:
            self.__condition.release()

    def run(self):
        """Main loop of NWS local server thread."""
        srv = NwsService()
        srv.startService()      #pylint: disable-msg=E1101
        try:
            #pylint: disable-msg=E1101,W0212
            self.__port = reactor.listenTCP(self.__desired_port, srv._factory)
            reactor.callWhenRunning(self.__set_started)
            reactor.run(installSignalHandlers=0)
        finally:
            srv.stopService()   #pylint: disable-msg=E1101

    def __set_started(self):
        """Callback from twisted indicating successful startup of the
        server."""
        self.__condition.acquire()
        try:
            self.__started = True
            self.__condition.notifyAll()
        finally:
            self.__condition.release()

