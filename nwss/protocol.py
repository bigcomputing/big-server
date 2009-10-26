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

"""Protocol implementation for NetWorkSpaces server."""

# TODO: In some cases, the client is expecting a long response and in some
#       cases, a short response.  In many error conditions, we send only a
#       short response...  Wacky Hijinks (TM) ensue.


import os, time
from tempfile import mkstemp
from twisted.protocols import stateful
from twisted.python import log
from twisted.internet import reactor
from nwss.base import Value, DIRECT_STRING, Response, ERROR_VALUE
from nwss.protoutils import DictReceiver, ArgTupleReceiver, FileProducer
from nwss.protoutils import map_proto_generator
import nwss

try:
    from twisted.internet.ssl import DefaultOpenSSLContextFactory
except ImportError:
    DefaultOpenSSLContextFactory = None  #pylint: disable-msg=C0103

_DEBUG = nwss.config.is_debug_enabled('NWS:protocol')

def server_configured_ssl():
    """Return True if the server has configured SSL support."""
    return (nwss.config.serversslkey  is not None and
            nwss.config.serversslcert is not None)

def clear_server_ssl_config():
    """Clear the server's SSL configuration to avoid spamming the logs."""
    nwss.config.serversslkey  = None
    nwss.config.serversslcert = None

def ssl_is_available():
    """Return True if the PyOpenSSL library is available on the server."""
    return DefaultOpenSSLContextFactory is not None

if server_configured_ssl()  and  not ssl_is_available():
    log.msg("Failed to import PyOpenSSL.  SSL support is disabled.")
    clear_server_ssl_config()

class WsSessionStats(object):
    """Counter for some informational statistics about a given NWS session."""

    def __init__(self):
        """Create a new session statistics counter."""
        self.__num_operations = 0
        self.__last_operation = ''
        self.__last_operation_time = ''
        self.__num_long_values = 0

    def mark_operation(self, opname):
        """Mark the occurrence of an operation, updating all relevant
        statistics."""
        self.__last_operation = opname
        self.__last_operation_time = time.asctime()
        self.__num_operations += 1

    def mark_new_long_value(self):
        """Mark the creation of a new long value, updating all relevant
        statistics."""
        self.__num_long_values += 1

    def __get_num_operations(self):
        """Get the number of operations we've performed since this session
        started."""
        return self.__num_operations
    num_operations = property(__get_num_operations)

    def __get_last_operation(self):
        """Get a tuple of the name and time of the last operation performed.
        For instance:

            ("store", "Sun Apr 19 20:04:42 PDT 2009")
        """
        return self.__last_operation, self.__last_operation_time
    last_operation = property(__get_last_operation)

    def __get_num_long_values(self):
        """Get the number of values which have been stored through this
        connection which have resulted in the creation of "long value" files.
        """
        return self.__num_long_values
    num_long_values = property(__get_num_long_values)

class WsBlockingInfo(object):
    """Manager for the 'blocking' state of a protocol object.  Responsible for
    ensuring that the protocol is on at most 1 waiter list, and is removed at
    the appropriate time."""

    def __init__(self):
        self.__blocking    = False
        self.__waiter_list = []     # Var's blocked clients list containing us
        self.__var         = None   # Var for which this conn. is blocking

    def block(self):
        """Put this session into the "blocking" state if it is not blocking
        already."""
        if self.__blocking:
            return False
        self.__blocking = True
        return True

    def clear(self):
        """If this connection was blocking, mark it as no longer so.  This will
        not remove the connection from any "waiter" lists, so if we may still
        be on a waiter list, we need to call remove_from_waiter_list first.
        """
        self.__blocking    = False
        self.__waiter_list = []
        self.__var         = None

    def remove(self, proto):
        """Remove us from whichever waiter list we appear in, if, indeed, we
        appear in a waiter list."""
        try:
            self.__waiter_list.remove(proto)
        except ValueError:
            if _DEBUG:
                log.msg("Blocked client was not in blocked clients list.")
        self.clear()

    def set_var(self, var, waiter_list):
        """Set the variable into whose waiter list this connection has been
        entered, as well as the waiter list itself.  When a value becomes
        availble, this information will be used to remove this connection from
        the appropriate waiter list."""
        self.__var = var
        self.__waiter_list = waiter_list

    def __is_blocking(self):
        """Check if this connection is currently waiting on a response from the
        server code.  This flag is briefly true for any operation, but may be
        true for an extended period of time if we are performing a blocking
        operation for a value not yet available."""
        return self.__blocking
    blocking = property(__is_blocking)

    def __get_var(self):
        """Get the variable in whose waiter lists we appear.  Used for
        monitoring purposes."""
        return self.__var
    var = property(__get_var)

def coerce_status(status):
    """Utility to coerce status to a 4-byte string in appropriate format
    for inclusion in the protocol.  This is primarily to handle the integer
    -> string case."""
    if isinstance(status, int):
        status = '%04d' % status
    elif not isinstance(status, str):
        log.msg('Internal error: status of %s [%s] returned to client' %
                      (str(status), str(type(status))))
        log.msg('Converting to string.')
        status = str(status)
    if len(status) != 4:
        log.msg('Internal error: status of %s returned to client' %
                      status)
        log.msg('Truncating to 4 bytes.')
        status = status[0:4]
    return status

class NwsProtocol(object, stateful.StatefulProtocol):
    #pylint: disable-msg=R0901,R0902
    """Twisted protocol object for NetWorkSpaces server.

       The generic structure of the protocol consists mostly of fixed length
       ASCII sequences.  The core of a NWS message consists of a 4-digit
       0-padded ASCII decimal count of the elements of a tuple, which must
       always have at least one argument.  The tuple elements are each
       serialized as a 20-digit 0-padded ASCII decimal length followed by raw
       bytes.  The first element of the tuple is always a command-name, of
       which a dozen or so valid values exist.

       A 20-digit count is used to allow accommodation of any 64-bit value.

       The interpretation of the remainder of the elements in the tuple depend
       on the specific command used.
    """

    DEFAULT_OPTIONS = {
            'MetadataToServer':    '',
            'MetadataFromServer':  '',
            'KillServerOnClose':   '',
    }
    if server_configured_ssl():
        DEFAULT_OPTIONS['SSL'] = ''

    def __init__(self):
        # Twisted will initialize 'factory' to point at the NwsService
        self.factory = None

        # Twisted will initialize 'peer' to point at details about the client
        # self.peer = None

        # Twisted stashes a unique id here for this client
        self.__protokey = -1

        # Connection options
        self.__metadata_receive = False
        self.__metadata_send = False
        self.__deadman = False
        self.__reply_long_preamble = self.__reply_long_preamble_nocookie

        # Session statistics
        self.__statistics = WsSessionStats()

        # Blocking info
        self.__blocking_state = WsBlockingInfo()

    def __str__(self):
        if hasattr(self, 'peer'):
            return 'NwsProtocol[%s]' % self.peer
        else:
            return 'NwsProtocol[not connected]'

    #######################################################
    # Overrides for Twisted methods
    #######################################################

    def connectionMade(self):
        #pylint: disable-msg=C0103
        """Callback from Twisted after a new connection is made.  Note that
        protocol objects are not reused, so the only real purpose of this
        method is to initialize state which requires access to the factory and
        transport objects."""
        self.transport.setTcpNoDelay(1)
        self.transport.setTcpKeepAlive(1)

        # HACK: dig through the factory for the web port, add it to the
        #       advertised options.
        if hasattr(self.factory, 'nwsWebPort'):
            port = str(self.factory.nwsWebPort())
            self.DEFAULT_OPTIONS['NwsWebPort'] = str(port)

    def connectionLost(self, reason):
        #pylint: disable-msg=C0103,W0222
        """Callback from Twisted to indicate that this connection has been
        shutdown.
        """
        if _DEBUG:
            log.msg('connectionLost called')
        self.factory.goodbye(self)
        if self.__deadman:
            log.msg('stopping the server due to deadman switch')
            #pylint: disable-msg=E1101
            reactor.stop()

    def getInitialState(self):
        #pylint: disable-msg=C0103
        """Callback from Twisted to find the start state for this protocol.
        The NWS protocol always begins with a 4-byte handshake."""
        return (self.__receive_handshake_request, 4)

    #######################################################
    # Interface exposed to server
    #######################################################

    def __get_protocol_key(self):
        """Attribute accessor for the "protocol key", which is actually a
        unique id for this client connection.  (One of several, since twisted
        also assigns a unique sessionid...)"""
        return self.__protokey

    def __set_protocol_key(self, key):
        """Attribute mutator for the "protocol key"."""
        self.__protokey = key
    protokey = property(__get_protocol_key, __set_protocol_key)

    def get_peer(self):
        """Get a semi-human-readable textual identifier for the host on the
        other side of the connection.  Generally something containing the IP
        address and port number for the remote side."""
        return str(self.transport.getPeer())
    peer = property(get_peer)

    def __get_num_operations(self):
        """Get the number of operations we've performed since connection
        creation."""
        return self.__statistics.num_operations
    num_operations = property(__get_num_operations)

    def __get_last_operation(self):
        """Get a tuple of the name and time of the last operation performed.
        For instance:

            ("store", "Sun Apr 19 20:04:42 PDT 2009")
        """
        return self.__statistics.last_operation
    last_operation = property(__get_last_operation)

    def __get_num_long_values(self):
        """Get the number of values which have been stored through this
        connection which have resulted in the creation of "long value" files.
        """
        return self.__statistics.num_long_values
    num_long_values = property(__get_num_long_values)

    def __is_blocking(self):
        """Check if this connection is currently waiting on a response from the
        server code."""
        return self.__blocking_state.blocking
    blocking = property(__is_blocking)

    def set_blocking_var(self, var, waiter_list):
        """Set the variable into whose waiter list this connection has been
        entered, as well as the waiter list itself."""
        self.__blocking_state.set_var(var, waiter_list)

    def __get_blocking_var(self):
        """Get the variable in whose waiter lists we appear.  Used for
        monitoring purposes."""
        return self.__blocking_state.var
    blocking_var = property(__get_blocking_var)

    def remove_from_waiter_list(self):
        """Remove us from whichever waiter list we appear in, if, indeed, we
        appear in a waiter list."""
        self.__blocking_state.remove(self)

    def mark_for_death(self):
        """Mark this connection as a deadman connection.  When this connection
        is closed, it will stop the reactor, resulting in the shutdown of the
        server."""
        self.__deadman = True

    def new_long_arg_file(self):
        """Allocate a new file for a long argument.  The file will be uniquely
        named and securely created in the NWS temporary directory."""
        self.__statistics.mark_new_long_value()
        try:
            filedesc, tmpname = mkstemp(prefix='__nwss',
                    suffix='.dat', dir=nwss.config.tmpdir)
            return os.fdopen(filedesc, 'w+b'), tmpname
        except OSError, exc:
            log.msg('error creating temporary file: ' + str(exc))
            return None

    #######################################################
    # Generic protocol utilities
    #######################################################

    def __send_dictionary(self, dictionary):
        """Marshal and write the contents of a dictionary to the transport in
        the canonical form, as interpreted by the DictReceiver utility."""
        maplen = len(dictionary)
        self.transport.write('%04d' % maplen)
        #pylint: disable-msg=W0141
        map(self.transport.write, map_proto_generator(dictionary))

    #######################################################
    # Handshake protocol machinery
    #######################################################

    def __receive_handshake_request(self, data):
        """Receive a handshake request from the client-side.  This is the entry
        point to the NWS protocol."""
        if _DEBUG:
            log.msg('handshake initiated with: ' + repr(data))

        # New-style handshake
        if data.startswith('X'):
            self.__reply_long_preamble = self.__reply_long_preamble_cookie
            self.__send_options_advertise(self.DEFAULT_OPTIONS)
            return (self.__receive_options_request, 4)

        # Old-style handshake
        if data not in ['0000', '1111']:
            self.__reply_long_preamble = self.__reply_long_preamble_cookie
        self.transport.write('2223')

        # Beginning of the protocol proper.
        return self.__get_command_state()

    def __send_options_advertise(self, opts):
        """Send an options advertisement to the client with a list of the
        options the server supports as well as required or forbidden
        options."""
        self.transport.write('P000')
        self.__send_dictionary(opts)

    def __receive_options_request(self, data):
        """Receive a "connection options" request packet from the client or
        terminate the connection."""
        if data != 'R000':
            log.msg('Client send invalid handshake response.')
            self.transport.loseConnection()

        receiver = DictReceiver(self, self.__receive_connection_options)
        return receiver.start, receiver.start_count

    def __receive_connection_options(self, options):
        """Callback from the protocol handlers when we have a handshake options
        negotiation request."""
        if self.__validate_connection_options(options):
            self.__process_connection_options(options)
            if options.get('SSL') == '1':
                if ssl_is_available():
                    key = nwss.config.serversslkey
                    cert = nwss.config.serversslcert
                    ctx = DefaultOpenSSLContextFactory(key, cert)
                    self.__send_accept_connection()
                    self.transport.startTLS(ctx)
                else:
                    # SSL requested, but not available server side
                    log.msg('Internal error: SSL not available.')
                    self.__send_deny_connection()
                    return None
            else:
                self.__send_accept_connection()
            return self.__get_command_state()
        else:
            self.__send_deny_connection()
            return None

    def __validate_connection_options(self, options):
        """Check that the requested connection options are compatible with our
        advertised options."""
        for opt, val in options.items():
            if not self.DEFAULT_OPTIONS.has_key(opt):
                return False
            elif (self.DEFAULT_OPTIONS[opt] != '' and
                  self.DEFAULT_OPTIONS[opt] != val):
                return False
        return True

    def __process_connection_options(self, options):
        """Read through the connection options, pulling out options which are
        of interest to us."""
        if options.get("KillServerOnClose") == "1":
            self.__deadman = True
        if options.get("MetadataToServer") == "1":
            self.__metadata_receive = True
        if options.get("MetadataFromServer") == "1":
            self.__metadata_send = True

    def __send_deny_connection(self):
        """Deny the client's connection request and shut down the
        connection."""
        self.transport.write('F000')
        self.transport.loseConnection()
        log.msg('Dropped connection after handshake: invalid option requested')

    def __send_accept_connection(self):
        """Accept the client's connection request."""
        self.transport.write('A000')

    #######################################################
    # Command protocol machinery
    #######################################################

    def __get_command_state(self):
        """Get the protocol state for the start of a new command request.  This
        varies depending on whether metadata from the client is enabled."""
        if self.__metadata_receive:
            return DictReceiver(self, self.__receive_metadata).start, 4
        else:
            return self.__get_args_state(metadata={})

    def __get_args_state(self, metadata):
        """Get the protocol state for the start of the arguments proper in a
        command request, populating the state with the specified metadata
        map."""
        return ArgTupleReceiver(self, self.__handle_command, metadata).start, 4

    def __receive_metadata(self, metadata):
        """Receive a metadata map from the client side and advance the protocol
        to the argument list state."""
        return self.__get_args_state(metadata)

    def __handle_command(self, args, metadata):
        """Handle a command from the client."""
        if not self.__blocking_state.block():
            self.send_error('Received a request while already blocking on a ' +
                            'command.')
            self.transport.loseConnection()
        if len(args) < 1:
            log.msg('Empty argument list')
            self.send_error('Received an empty argument list.')
            self.transport.loseConnection()
            return None
        #pylint: disable-msg=W0142
        self.factory.handle_command(self, metadata, *args)
        self.__statistics.mark_operation(args[0])
        return self.__get_command_state()

    def __reply_long_preamble_cookie(self, response):
        """Send the "cookie protocol" version of a long reply preamble."""
        self.transport.write('%s%020d%-20.20s%020d%020d' %
            (response.status,
             response.value.type_descriptor,
             response.iterstate[0],
             response.iterstate[1],
             response.value.length()))

    def __reply_long_preamble_nocookie(self, response):
        #pylint: disable-msg=W0613
        """Send the no-"cookie protocol" version of a long reply preamble."""
        self.transport.write('%s%020d%020d' %
              (response.status,
               response.value.type_descriptor,
               response.value.length()))

    def send_error(self, reason, status=1, long_reply=False):
        """Utility to send an error reply."""
        metadata = { 'nwsReason': reason }
        response = Response(metadata)
        response.status = status
        if long_reply:
            response.value = ERROR_VALUE
            self.send_long_response(response)
        else:
            self.send_short_response(response)

    def send_short_response(self, response=None):
        """Send a response to a query which expects a "short" response."""
        if response is None:
            response = Response()
        assert response.value is None
        assert response.iterstate is None

        # This operation is obviously no longer blocking
        self.__blocking_state.clear()

        # Coerce the status to a 4-digit string
        response.status = coerce_status(response.status)

        # Send the metadata
        if self.__metadata_send:
            self.__send_dictionary(response.metadata)

        # Send the reply
        self.transport.write(response.status)

    def send_long_response(self, response=None):
        """Send a response to a query which expects a "long" response."""
        if response is None:
            response = Response(value=ERROR_VALUE)
        assert response.value is not None
        if response.iterstate is None:
            response.iterstate = ('', 0)

        # This operation is obviously no longer blocking
        self.__blocking_state.clear()

        # Coerce the response to a Value
        if not isinstance(response.value, Value):
            response.value = str(response.value)
        if isinstance(response.value, str):
            response.value = Value(DIRECT_STRING, response.value)

        # Coerce the status to a 4-digit string
        response.status = coerce_status(response.status)

        # Send the metadata
        if self.__metadata_send:
            self.__send_dictionary(response.metadata)

        # Send the reply itself
        self.__reply_long_preamble(response)
        if response.value.is_large():
            if _DEBUG:
                log.msg("using long value protocol")
            producer = FileProducer(response.value, self.transport)
            self.transport.registerProducer(producer, None)
        else:
            self.transport.write(response.value.val())
