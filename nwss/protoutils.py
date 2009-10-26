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

"""Miscellaneous utilities and building blocks for the NWS protocol."""

from twisted.python import log
import nwss
import os

_MIN_LONG_VALUE_SIZE = 64
_BUFFER_SIZE = 16 * 1024
_DEBUG = nwss.config.is_debug_enabled('NWS:protoutils')

try:
    set()                               #pylint: disable-msg=W8302
except NameError:
    from sets import Set as set         #pylint: disable-msg=W0622

class WsNameMap(object):
    """'External-to-internal' name mapping for workspaces.  This was separated
    into a mixin so that it can be used in DummyConnection as well."""

    def __init__(self):
        """Create a new ext-to-int workspace name mapping."""
        self.__ext_to_int_names = {}

    def get(self, ext_name):
        """Lookup the internal name for an external workspace name.  Returns
        None if the named workspace doesn't exist."""
        return self.__ext_to_int_names.get(ext_name)

    def set(self, ext_name, int_name):
        """Set the internal name for an external workspace name."""
        self.__ext_to_int_names[ext_name] = int_name

    def remove(self, ext_name):
        """Clear the mapping for an internal name for a given external
        workspace name.  No error is raised if the name didn't exist."""
        try:
            del self.__ext_to_int_names[ext_name]
        except KeyError:
            pass

class WsTracker(object):
    """List of 'owned' workspaces, tracked by internal name.  Separated into a
    mixin so that it can be used in DummyConnection as well."""

    def __init__(self):
        """Create a new owned workspace list."""
        self.__owned_workspaces = set()

    def add(self, int_name):
        """Add a workspace to our ownership list."""
        self.__owned_workspaces.add(int_name)

    def remove(self, int_name):
        """Remove a workspace from our ownership list."""
        try:
            self.__owned_workspaces.remove(int_name)
            return True
        except KeyError:
            return False

    def contains(self, int_name):
        """Check if we claim ownership of a given workspace."""
        return (int_name in self.__owned_workspaces)

    def as_list(self):
        """Get a list of workspaces owned by us."""
        return list(self.__owned_workspaces)

    def get_count(self):
        """Get a count of the workspaces owned by us."""
        return len(self.__owned_workspaces)
    count = property(get_count)

    def clear(self):
        """Clear all workspaces from our list."""
        self.__owned_workspaces.clear()


class CountedReceiver(object):
    """Protocol helper class for protocol atoms which consist of a fixed-length
    ASCII decimal byte count followed by raw data.  Most data in the NWS
    protocol adheres to this format with either a 4-byte or 20-byte count.

    Generally, this class is used from a protocol object as:

        return CountedReceiver(self, self.set_my_value).start, 4
    """

    def __init__(self, conn, target, start_count=4):
        """Create a new CountedReceiver protocol atom.

           Parameters:
               conn        - the protocol object on whose behalf we act
               target      - function to receive the data
               start_count - size of count (in bytes) [default: 4]
        """
        self.__conn = conn
        self.__target = target
        self.start_count = start_count

    def get_target(self):
        """Get the target of this protocol helper."""
        return self.__target
    target = property(get_target)

    def get_connection(self):
        """Get the Protocol object for this protocol helper."""
        return self.__conn
    connection = property(get_connection)

    def start(self, data):
        """The start state for this atom.  This is the method to pass to
        twisted as the handler for the chunk of data on a newly created atom.
        """
        try:
            length = int(data)
            if length < 0:
                raise ValueError('negative argument length')
        except ValueError:
            log.msg("error: got bad data from client")
            self.__conn.transport.loseConnection()
            return None
        return self.__target, length

class CountedReceiverLong(CountedReceiver):
    """Specialized protocol helper class for protocol atoms identical to those
    supported by CountedReceiver, with a count occupying 20 bytes.  The
    important difference is that this atom supports saving large data directly
    to a file.  As a result, the 'target' must support an optional boolean
    argument 'long_data'.  If True, the data passed to the target will be a
    filename, rather than the data itself.

    Generally, this class is used from a protocol object as:

        return CountedReceiverLong(self, self.set_my_value).start, 20
    """

    def __init__(self, conn, target):
        """Create a new CountedReceiverLong protocol atom.

           Parameters:
               conn        - the protocol object on whose behalf we act
               target      - function to receive the data
        """
        CountedReceiver.__init__(self, conn, target, 20)
        self.__target = target
        self.__conn = conn
        self.__file = None
        self.__filename = None
        self.__remain_length = 0

    def start(self, data):
        """The start state for this atom.  This is the method to pass to
        twisted as the handler for the chunk of data on a newly created atom.
        """
        base_next = CountedReceiver.start(self, data)
        if base_next is None:
            return None
        _, length = base_next

        # Compute the threshold for treating the value as long data
        threshold = max(_MIN_LONG_VALUE_SIZE, nwss.config.nwsLongValueSize)

        if length >= threshold:

            # Set up the streaming transfer
            self.__remain_length = length
            tmpfile = self.__conn.new_long_arg_file()
            if tmpfile == None:
                # Failed to create the file, but still need to ride out the
                # transfer.
                self.__file = None
            else:
                self.__file, self.__filename = tmpfile
            return self.long_data, min(_BUFFER_SIZE, length)
        else:
            return base_next

    def long_data(self, data):
        """The streaming data state for this atom.  This state is entered only
        if the length of the data exceeds the long-data threshold, and will be
        re-entered repeatedly until all data has been read.
        """
        self.__remain_length -= len(data)
        if self.__file != None:
            self.__file.write(data)
            if self.__remain_length <= 0:
                self.__file.close()
                return self.__target(self.__filename, long_data=True)
        else:
            if self.__remain_length <= 0:
                self.__conn.send_error('Failed to read long data from the ' +
                                       'filesystem.')
                self.__conn.transport.loseConnection()
                return None
        return self.long_data, min(_BUFFER_SIZE, self.__remain_length)

class NameValueReceiver(object):
    """Specialized protocol helper class for protocol elements consisting of
    two consecutive CountedReceiver atoms representing names and values.  The
    target will receive a (name, value) tuple.

    Generally, this class is used from a protocol object as:

        return NameValueReceiver(self, self.add_entry).start, 4
    """

    start_count = 4

    def __init__(self, conn, target):
        """Create a new NameValueReceiver protocol atom.

           Parameters:
               conn        - the protocol object on whose behalf we act
               target      - function to receive the data
        """
        self.__conn   = conn
        self.__target = target
        self.__name   = None

    def get_start(self):
        """Get the start state for this atom.  Note: unlike the preceding
        helpers, this is NOT a handler to be passed to twisted, as it needs to
        delegate to a counted receiver instead.  Thanks to the 'start' property
        defined below, however, the notation is the same.
        """
        return CountedReceiver(self.__conn, self.name).start
    start = property(get_start)

    def name(self, data):
        """Target to receive name of name/value pair."""
        self.__name = data
        return CountedReceiver(self.__conn, self.value).start, 4

    def value(self, data):
        """Target to receive value of name/value pair."""
        return self.__target((self.__name, data))

class ListReceiver(object):
    """Specialized protocol helper class for protocol elements consisting of a
    4-byte ASCII decimal count followed by a series of protocol elements of a
    given format.

    Two callback functions should be provided.  One will be called for each
    item in the list, and the other will be called when all items have been
    received.

    Generally, this class is used from a protocol object as:

        return ListReceiver(self,
                            ItemReceiver,
                            self.add_item,
                            self.last_item).start, 4
    """

    start_count = 4

    def __init__(self, conn, item, target, done):
        """Create a new ListReceiver protocol element.

           Parameters:
               conn        - the protocol object on whose behalf we act
               item        - item type to read for list
               target      - function to receive each item
               done        - function called when all items have been received
        """
        self.__conn = conn
        self.__target = target
        self.__done = done
        self.__item_type = item
        self.__remaining = 0

    def start(self, data):
        """The start state for this atom.  This is the method to pass to
        twisted as the handler for the chunk of data on a newly created atom.
        """

        # Read the length
        try:
            length = int(data)
            if length < 0:
                raise ValueError('Negative count for item list.')
        except ValueError, exc:
            log.msg('Malformed protocol message: %s' % exc.args[0])
            self.__conn.transport.loseConnection()
            return None

        # Start reading the first item
        self.__remaining = length
        if self.__remaining == 0:
            return self.__done()
        else:
            item = self.__item_type(self.__conn, self.item)
            return item.start, item.start_count

    def item(self, data, **kwargs):
        """The callback for each item."""

        self.__remaining -= 1
        self.__target(data, **kwargs)
        if self.__remaining == 0:
            return self.__done()
        else:
            item = self.__item_type(self.__conn, self.item)
            return item.start, item.start_count

class DictReceiver(ListReceiver):
    """Specialized protocol helper class for protocol elements consisting of a
    stream of name-value pairs.  The format is that of a ListReceiver receiving
    NameValueReceiver elements.

    A callback function will receive a dictionary of all name-value pairs once
    they have all been read in.

    Generally, this class is used from a protocol object as:

        return DictReceiver(self, self.set_dictionary).start, 4

    or:

        dr = DictReceiver(self, self.__receive_connection_options)
        return dr.start, dr.start_count
    """

    def __init__(self, conn, target):
        """Create a new DictReceiver protocol element.

           Parameters:
               conn        - the protocol object on whose behalf we act
               target      - function to receive the complete dictionary
        """
        ListReceiver.__init__(self,
                              conn,
                              NameValueReceiver,
                              self.entry,
                              self.finished)
        self.__target = target
        self.__entries = {}

    def entry(self, data):
        """Callback to receive each name, value pair."""
        name, value = data
        self.__entries[name] = value

    def finished(self):
        """Callback upon completion."""
        return self.__target(self.__entries)

class ArgTupleReceiver(ListReceiver):
    """Specialized protocol helper class for protocol elements consisting of a
    stream of arguments.  The format is that of a ListReceiver receiving
    CountedReceiverLong elements.

    A callback function will receive a list of all arguments once they have all
    been read in.  The elements of the list will be strings and, for "long"
    items, tuples of filename and content length.

    Generally, this class is used from a protocol object as:

        return ArgTupleReceiver(self, self.set_args).start, 4

    or:

        atr = ArgTupleReceiver(self, self.set_args)
        return atr.start, atr.start_count
    """

    def __init__(self, conn, target, metadata):
        """Create a new ArgTupleReceiver protocol element.

           Parameters:
               conn        - the protocol object on whose behalf we act
               target      - function to receive the complete argument list
               metadata    - metadata attached to this arg tuple, if any
        """
        ListReceiver.__init__(self,
                              conn,
                              CountedReceiverLong,
                              self.next_arg,
                              self.finished)
        self.__target = target
        self.__args = []
        self.__metadata = metadata

    def next_arg(self, data, long_data=False):
        """Callback to receive each argument.  If long_data is True, the data
        contains a filename rather than directly containing the data."""
        if long_data:
            dlen = os.stat(data).st_size
            data = (data, dlen)
        self.__args.append(data)

    def finished(self):
        """Callback upon completion."""
        return self.__target(self.__args, self.__metadata)

class FileProducer(object):
    """Twisted "producer" to allow drawing data directly from a file on
    disk."""

    def __init__(self, value, transport):
        """Create a new file producer for a given value object.

           Parameters:
               value        - the value
               transport    - consumer of data
        """
        self.__value = value
        self.__file = value.get_file()
        self.__buffer_size = _BUFFER_SIZE
        self.__transport = transport
        self.__finished = False

    def stopProducing(self):
        #pylint: disable-msg=C0103
        """Implementation of IPushProducer.stopProducing method from Twisted.
        Called to abort production of data from the file."""
        if _DEBUG:
            log.msg('stopProducing called')
        if not self.__finished:
            if _DEBUG:
                log.msg('stopProducing unregistering producer')
            try:
                self.__file.close()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception:               #pylint: disable-msg=W0703
                pass
            self.__transport.unregisterProducer()
            self.__finished = True
            self.__value.access_complete()
        else:
            log.msg("error: stopProducing called even though I finished")

    def resumeProducing(self):
        #pylint: disable-msg=C0103
        """Implementation of IPushProducer.resumeProducing method from Twisted.
        Called to resume production of data from the file after it has been
        paused."""
        # read some more data from the file, a write it to the transport
        if _DEBUG:
            log.msg('resumeProducing called')
        if not self.__finished:
            if _DEBUG:
                log.msg('resumeProducing reading file')
            data = self.__file.read(self.__buffer_size)

            if not data:
                if _DEBUG:
                    log.msg('resumeProducing unregistering producer')
                try:
                    self.__file.close()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception:           #pylint: disable-msg=W0703
                    pass
                self.__transport.unregisterProducer()
                self.__finished = True
                self.__value.access_complete()
            else:
                if _DEBUG:
                    log.msg('resumeProducing sending data to client ' + data)
                self.__transport.write(data)
        else:
            log.msg("error: resumeProducing called even though I unregistered")

    def pauseProducing(self):
        #pylint: disable-msg=C0103,R0201
        """Implementation of IPushProducer.pauseProducing method from Twisted.
        Called to resume production of data from the file after it has been
        paused.  Even though this method does nothing, it must be present in
        order for this class to implement the IPushProducer interface."""
        if _DEBUG:
            log.msg('pauseProducing called')

def map_proto_generator(data):
    """Utility which turns a map into a stream of name value pairs in the
    correct protocol form for metadata maps."""
    return [('%04d%s%04d%s' % (len(k), k, len(v), v)) for k, v in data.items()]

