#
# Copyright (c) 2005-2009, REvolution Computing, Inc.
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

import sys, os, inspect
import win32serviceutil, win32service, win32event, win32process, win32api
from nwss.util import msc_argv2str

# XXX: should be a better way than this: maybe the registry?
# try to find the Python installation directory
_PYTHONDIR = os.path.dirname(inspect.getfile(win32api))
while not os.path.isfile(os.path.join(_PYTHONDIR, 'python.exe')) and \
        os.path.basename(_PYTHONDIR):
    _PYTHONDIR = os.path.dirname(_PYTHONDIR)

_INTERP = _PYTHONDIR + '\\python.exe'  # XXX: should this use pythonw.exe?
_SCRIPT = _PYTHONDIR + '\\scripts\\twistd.py'
_TACFILE = _PYTHONDIR + '\\nws.tac'
_LOGFILE = _PYTHONDIR + '\\nws.log'

# nws server states
_NWS_SERVER_RUNNING = 100
_NWS_SERVER_DIED = 101
_NWS_SERVER_RESTARTED = 102

# timeouts
_DIED_TIMEOUT = 10 * 1000       # milliseconds to wait before restarting
                                # a dead nws server
_RESTARTED_TIMEOUT = 10 * 1000  # milliseconds to wait before considering a
                                # restarted nws server to be running

class NwsService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'NwsService'
    _svc_display_name_ = 'NetWorkSpaces Service'
    _svc_description_ = 'Enables multiple independent applications written in ' \
            'scripting languages to share data and coordinate their computations. ' \
            'Client support currently exists for R, Python, and Matlab.'

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.applicationName = _INTERP
        argv = [self.applicationName, _SCRIPT, '-o', '-l', _LOGFILE, '-y', _TACFILE]
        self.commandLine = msc_argv2str(argv)

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        import servicemanager
        self.sm = servicemanager
        self.sm.LogMsg(self.sm.EVENTLOG_INFORMATION_TYPE,
                self.sm.PYS_SERVICE_STARTED, (self._svc_name_, ''))

        self.procHandle = self._startNws()
        handles = (self.hWaitStop, self.procHandle)
        timeout = win32event.INFINITE
        state = _NWS_SERVER_RUNNING

        while True:            
            # wait for a stop request, a nws server death, or possibly a timeout
            s = win32event.WaitForMultipleObjects(handles, 0, timeout)

            if s == win32event.WAIT_TIMEOUT:
                if state == _NWS_SERVER_RESTARTED:
                    self._info("nws server restarted successfully")
                    timeout = win32event.INFINITE
                    state = _NWS_SERVER_RUNNING
                elif state == _NWS_SERVER_DIED:
                    self.procHandle = self._startNws()
                    handles = (self.hWaitStop, self.procHandle)
                    timeout = _RESTARTED_TIMEOUT
                    state = _NWS_SERVER_RESTARTED
                else:
                    self._error("got an unexpected timeout while in state %d" % state)
                    break
            elif s == win32event.WAIT_OBJECT_0:
                # a shutdown was requested, so kill the nws server
                # and break out of the while loop
                if self.procHandle:
                    self._info("shutdown requested: terminating nws server")
                    try:
                        win32process.TerminateProcess(self.procHandle, 0)
                    except:
                        e = sys.exc_info()[1]
                        self._info("caught exception terminating nws server: %s" % str(e))
                else:
                    self._info("shutdown requested while no nws server running")
                break
            elif s == win32event.WAIT_OBJECT_0 + 1:
                # the nws server exited by itself, which probably means
                # that the NWS server shutdown.  we want to reconnect
                # when it comes back up, so sleep awhile, and then
                # start another nws server.  this will probably happen
                # over and over again, so don't do it too frequently.
                if state == _NWS_SERVER_RUNNING:
                    self._info("nws server died: restarting in a bit")

                win32api.CloseHandle(self.procHandle)
                self.procHandle = None
                handles = (self.hWaitStop,)
                timeout = _DIED_TIMEOUT
                state = _NWS_SERVER_DIED
            else:
                self._error("illegal status from WaitForMultipleObjects: stopping")
                break

        self.sm.LogMsg(self.sm.EVENTLOG_INFORMATION_TYPE,
                self.sm.PYS_SERVICE_STOPPED, (self._svc_name_, ''))

    def _info(self, msg):
        self.sm.LogMsg(self.sm.EVENTLOG_INFORMATION_TYPE, 1, (msg,))

    def _error(self, msg):
        self.sm.LogMsg(self.sm.EVENTLOG_ERROR_TYPE, 1, (msg,))

    def _startNws(self):
        processSecurityAttributes = None
        threadSecurityAttributes = None
        fInheritHandles = 0
        creationFlags = win32process.CREATE_NO_WINDOW
        environment = None
        currentDirectory = None
        startupInfo = win32process.STARTUPINFO()

        procHandle, threadHandle, procId, threadId = win32process.CreateProcess(
                self.applicationName, self.commandLine,
                processSecurityAttributes, threadSecurityAttributes,
                fInheritHandles, creationFlags,
                environment, currentDirectory,
                startupInfo)

        win32api.CloseHandle(threadHandle)

        return procHandle

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(NwsService)
