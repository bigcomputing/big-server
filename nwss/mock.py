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

"""Mock objects, used both for testing and for the internal plumbing of the
Babelfish and monitors.
"""

# these dummy classes are used by the objects that want to pretend
# they are clients of the nws server.

from twisted.python import log
from nwss.protoutils import WsTracker, WsNameMap
from nwss.base import DIRECT_STRING, ERROR_VALUE
from nwss.base import Response, Value
import nwss

_DEBUG = nwss.config.is_debug_enabled('NWS:mock')

__all__ = ['MockTransport', 'MockConnection', 'DummyConnection']

class MockTransport(object):
    #pylint: disable-msg=R0903
    """Mock 'transport' object, mimicking the various transport objects from
    Twisted.  Presently, only used indirectly (i.e. as part of a
    DummyConnection).
    """

    def __init__(self):
        self.sessionno = -1

    def write(self, data):
        #pylint: disable-msg=R0201
        """Override of Twisted 'write' method."""
        if _DEBUG:
            log.msg("MockTransport.write: data = %s" % repr(data))

class MockConnection(object):
    #pylint: disable-msg=R0903
    """Mock 'connection' object, mimicking the interface of the NwsProtocol
    object in a fairly minimal way.
    """

    transport_factory = MockTransport

    def __init__(self, peer_id='[Mock]'):
        """Initialize a new mock connection:

          Parameters:
              peer_id               - peer id to report in monitoring
        """
        self.owned_workspaces = WsTracker()
        self.workspace_names = WsNameMap()

        self.peer = peer_id
        self.transport = self.transport_factory()

    def set_blocking_var(self, var, blocklist):
        """Set the currently "blocking" variable."""
        pass

    def send_short_response(self, response=None):
        #pylint: disable-msg=R0201
        """Implementation of NwsProtocol 'send_short_response' interface."""
        pass

    def send_long_response(self, response):
        #pylint: disable-msg=R0201
        """Implementation of NwsProtocol 'send_long_response' interface."""
        if response is None:
            response = Response(value=ERROR_VALUE)
        assert response.value is not None

    def send_error(self, reason, status=1, long_reply=False):
        """Send an error message to the other side."""
        pass

class DummyConnection(MockConnection):
    #pylint: disable-msg=R0903
    """Simple dummy 'connection' object, used throughout the web interface."""

    def __init__(self, send_reply=None, peer_id='[Web Interface]'):
        """Initialize a new dummy connection:

          Parameters:
              send_reply            - function to receive replies
              peer_id               - peer id to report in monitoring
        """
        MockConnection.__init__(self, peer_id)
        if send_reply:
            self.real_send_reply = send_reply

    def __str__(self):
        return 'DummyConnection[%s]' % self.peer

    def send_long_response(self, response):
        """Implementation of NwsProtocol 'send_long_response' interface."""
        if response is None:
            response = Response(value=ERROR_VALUE)
        assert response.value is not None
        if hasattr(self, 'real_send_reply'):
            status   = response.status
            metadata = response.metadata
            value    = response.value
            if isinstance(value, str):
                value = Value(DIRECT_STRING, value)
            return self.real_send_reply(status,
                                        metadata,
                                        value)
        else:
            return None
