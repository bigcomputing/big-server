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

"""
Core NetWorkSpaces server - variables implementation.
"""

from __future__ import generators
import time
from twisted.python import log

from nwss.pyutils import new_list, remove_first, clear_list
from nwss.base import BadModeException
from nwss.base import WorkspaceFailure
from nwss.base import Response, Value
import nwss

_DEBUG = nwss.config.is_debug_enabled('NWS:stdvars')

class BaseVar(object):
    """Base class for variables to simplify implementation of different
    variable types.
    """

    def __init__(self, name):
        """Constructor for BaseVar objects.

          Parameters:
            name               - user-readable name for var
        """
        self.__name = name
        self.vid = None
        self.fetchers = []
        self.finders = []

    def __get_name(self):
        """Get the name of this container."""
        return self.__name
    name = property(__get_name)

    def __get_num_fetchers(self):
        """Accessor for fetcher count property."""
        return len(self.fetchers)
    num_fetchers = property(__get_num_fetchers)

    def __get_num_finders(self):
        """Accessor for finder count property."""
        return len(self.finders)
    num_finders = property(__get_num_finders)

    def add_fetcher(self, fetcher):
        """Add a fetcher to this variable.

          Arguments:
            fetcher -- the fetcher to add
        """
        self.fetchers.append(fetcher)
        fetcher.set_blocking_var(self.__name, self.fetchers)

    def add_finder(self, finder):
        """Add a finder to this variable.

          Arguments:
            finder -- the finder to add
        """
        self.finders.append(finder)
        finder.set_blocking_var(self.__name, self.finders)

    def new_value(self, val_index, val, metadata):
        """Announce the appearance of a new value.

        If there are prior finders, the value will be distributed to them.  If
        there are prior fetchers, the value will be distributed to the first of
        them in line, and False will be returned.

          Arguments:
            val_index   - index of value being stored (for iterated finds, etc)
            val         - newly stored value
            metadata    - metadata stored with value
        """

        # Not consumed unless there was a fetcher
        consumed = False

        # Build response
        resp = Response(metadata, val)
        resp.iterstate = (self.vid, val_index)

        # feed the finders
        for client in self.finders:
            if _DEBUG:
                log.msg('calling finder session %d with val_index %d' %
                        (client.transport.sessionno, val_index))
            client.send_long_response(resp)

        # clear the finders list
        del self.finders[:]

        # give it to a fetcher if there is one
        if self.fetchers:
            client = self.fetchers.pop(0)
            if _DEBUG:
                log.msg('calling fetcher session %d with val_index %d' %
                        (client.transport.sessionno, val_index))
            client.send_long_response(resp)
            consumed = True

        return consumed

    def fail_waiters(self, reason):
        """Cause all waiters to fail, typically because this variable has been
        destroyed."""
        for client in self.fetchers:
            if _DEBUG:
                log.msg('sending error value to fetcher session %d' %
                             client.transport.sessionno)
            client.send_error(reason, long_reply=True)

        for client in self.finders:
            if _DEBUG:
                log.msg('sending error value to finder session %d' %
                             client.transport.sessionno)
            client.send_error(reason, long_reply=True)

        del self.fetchers[:]
        del self.finders[:]

class Fifo(BaseVar):
    """Variable class for FIFO-type variables."""

    def __init__(self, name):
        """Constructor for FIFO-type variables.

          Arguments:
            name         - user-readable name for var
        """
        BaseVar.__init__(self, name)

        self._contents = new_list()
        self._metadata = new_list()

        self._index = 0

    def __len__(self):
        return len(self._contents)

    def __iter__(self):
        return iter(self._contents)

    def store(self, client, value, metadata):
        #pylint: disable-msg=W0613
        """Handle a store request on this variable.

        For a FIFO variable, this adds a value to the tail of the values queue.

          Arguments:
            client -- client for whom to perform store
            value  -- value to store in FIFO
        """
        # compute the index of this incoming value in case we
        # need to give it to any waiting clients.
        # it isn't used for anything else
        val_index = self._index + len(self._contents)

        if self.new_value(val_index, value, metadata):
            # value was consumed, so increment index
            self._index += 1
        else:
            # value wasn't consumed, so save it
            self._contents.append(value)
            self._metadata.append(metadata)

    def fetch(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a fetch request on this variable.

          Arguments:
            client     - client for whom to perform fetch
            blocking   - is this a blocking fetch?
            val_index  - index of value to fetch (unused here)
        """
        fetch_location = max(val_index - self._index + 1, 0)
        if fetch_location > 0:
            raise WorkspaceFailure(
                    'ifetch* only supported at beginning of FIFO')
        try:
            value = remove_first(self._contents)
            var_metadata = remove_first(self._metadata)
            value.consumed()
            response = Response(var_metadata, value)
            response.iterstate = (self.vid, self._index)
            self._index += 1
            return response
        except IndexError:
            if blocking:
                self.add_fetcher(client)
                return None
            else:
                raise WorkspaceFailure('no value available')

    def find(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a find request on this variable.

          Arguments:
            client      - client for whom to perform find
            blocking    - is this a blocking find?
            val_index   - index of value to find (for iterated find)
        """
        try:
            find_location = max(val_index - self._index + 1, 0)
            response = Response(self._metadata[find_location],
                                self._contents[find_location])
            response.iterstate = self.vid, self._index + find_location
            return response

        except IndexError:
            if blocking:
                self.add_finder(client)
                return None
            else:
                raise WorkspaceFailure('no value available')

    def purge(self):
        """Purge this variable from the workspace, causing any clients waiting
        for a value to fail.
        """
        self.fail_waiters('Variable purged.')
        for val in self._contents:
            if isinstance(val, Value):
                val.close()

        clear_list(self._contents)
        clear_list(self._metadata)

class Lifo(BaseVar):
    """Variable class for LIFO-type variables."""

    def __init__(self, name):
        """Constructor for FIFO-type variables.

          Arguments:
            name            - user-readable name for var
        """
        BaseVar.__init__(self, name)
        self._contents = []
        self._metadata = []

    def __len__(self):
        return len(self._contents)

    def __iter__(self):
        return iter(self._contents)

    def store(self, client, value, metadata):
        #pylint: disable-msg=W0613
        """Handle a store request on this variable.

        For a LIFO variable, this adds a value to the tail of the values stack.

          Arguments:
            client -- client for whom to perform store
            value  -- value to store in LIFO
        """
        if not self.new_value(0, value, metadata):
            self._contents.append(value)
            self._metadata.append(metadata)

    def fetch(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a fetch request on this variable.

          Arguments:
            client       - client for whom to perform fetch
            blocking     - is this a blocking fetch?
            val_index    - index of value to fetch (unused here)
        """
        if val_index >= 0:
            raise WorkspaceFailure('ifetch* not supported on LIFO')
        try:
            value        = self._contents.pop()
            var_metadata = self._metadata.pop()
            value.consumed()
            return Response(var_metadata, value)
        except IndexError:
            if blocking:
                self.add_fetcher(client)
                return None
            else:
                raise WorkspaceFailure('no value available')

    def find(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a find request on this variable.

          Arguments:
            client       - client for whom to perform find
            blocking     - is this a blocking find?
            val_index    - index of value to find (for iterated find)
        """
        if val_index >= 0:
            raise WorkspaceFailure('ifind* not supported on LIFO')
        try:
            # ignore val_index since we don't allow iterators
            return Response(self._metadata[-1], self._contents[-1])
        except IndexError:
            if blocking:
                self.add_finder(client)
                return None
            else:
                raise WorkspaceFailure('no value available')

    def purge(self):
        """Purge this variable from the workspace, causing any clients waiting
        for a value to fail.
        """
        self.fail_waiters('Variable purged.')
        for val in self._contents:
            val.close()
        del self._contents[:]
        del self._metadata[:]

class Single(BaseVar):
    """Variable class for Single-type variables."""

    def __init__(self, name):
        """Constructor for Single-type variables.

          Arguments:
            name            - user-readable name for var
        """
        BaseVar.__init__(self, name)
        self._contents = []
        self._metadata = None
        self._index = 0

    def __len__(self):
        return self._contents and 1 or 0

    def __iter__(self):
        return iter(self._contents)

    def store(self, client, value, metadata):
        #pylint: disable-msg=W0613
        """Handle a store request on this variable.

        For a Single variable, this sets the value or feeds it to the first
        waiting fetcher.

          Arguments:
            client -- client for whom to perform store
            value  -- value to store in Single
        """
        # compute the index of this incoming value in case we
        # need to give it to any waiting clients.
        # it isn't used for anything else
        val_index = self._index + len(self)

        if self.new_value(val_index, value, metadata):
            # value was consumed, so increment index
            self._index += 1
        else:
            # value wasn't consumed, so save it
            if self._contents:
                self._contents[0].close()
                self._contents[0] = value
                self._index += 1
            else:
                self._contents.append(value)
            self._metadata = metadata

    def fetch(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a fetch request on this variable.

          Arguments:
            client   -- client for whom to perform fetch
            blocking -- is this a blocking fetch?
            val_index -- index of value to fetch (unused here)
        """
        try:
            fetch_location = max(val_index - self._index + 1, 0)
            value = self._contents.pop(fetch_location)
            value.consumed()
            response = Response(self._metadata, value)
            response.iterstate = (self.vid, self._index)
            self._metadata = None
            self._index += 1
            return response
        except IndexError:
            if blocking:
                self.add_fetcher(client)
                return None
            else:
                raise WorkspaceFailure('no value available')

    def find(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a find request on this variable.

          Arguments:
            client   -- client for whom to perform find
            blocking -- is this a blocking find?
            val_index -- index of value to find (for iterated find)
        """
        try:
            find_location = max(val_index - self._index + 1, 0)
            response = Response(self._metadata, self._contents[find_location])
            response.iterstate = (self.vid, self._index + find_location)
            return response
        except IndexError:
            if blocking:
                if _DEBUG:
                    log.msg('queueing up blocking find request')
                self.add_finder(client)
                return None
            else:
                if _DEBUG:
                    log.msg('returning unsuccessful reply')
                raise WorkspaceFailure('no value available')

    def purge(self):
        """Purge this variable from the workspace, causing any clients waiting
        for a value to fail.
        """
        self.fail_waiters('Variable purged.')
        if self._contents:
            self._contents[0].close()
            del self._contents[:]
        self._metadata = None

class SimpleAttribute(BaseVar):
    """Container type to hold a constant value, ignoring store requests and
    always allowing fetch/find requests to succeed.
    """
    def __init__(self, name, value_func, metadata=None):
        BaseVar.__init__(self, name)
        self.__value_func = value_func
        if metadata is None:
            self.__metadata = {}
        else:
            self.__metadata = metadata

    def __len__(self):
        return 1

    def __iter__(self):
        def singleton():
            """Single item iterator."""
            yield self.__value_func()
        return singleton()

    def new_value(self, val_index, val, metadata):
        """Announce the appearance of a new value.  This should never happen
        for this variable type.

          Arguments:
            val_index   - index of value being stored (for iterated finds, etc)
            val         - newly stored value
            metadata    - metadata stored with value
        """
        assert self.num_finders == 0
        assert self.num_fetchers == 0
        return False

    def store(self, client, value, metadata):
        #pylint: disable-msg=W0613,R0201
        """Handle a store request on this variable.

        For a constant, a store request is always an error.

          Arguments:
            client      - client for whom to perform store
            value       - value to store
            metadata    - metadata for store operation
        """
        raise WorkspaceFailure('Store is not supported for this variable.')

    def fetch(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a fetch request on this variable.

        For a constant, a fetch request always returns the same value.

          Arguments:
            client      - client for whom to perform fetch
            blocking    - is this a blocking operation
            val_index   - value index to fetch (irrelevant)
            metadata    - metadata for fetch operation
        """
        value = self.__value_func()
        return Response(self.__metadata, value)
    find = fetch

    def purge(self):
        """Purge this variable from the workspace, causing any clients waiting
        for a value to fail.  There should never be clients waiting on this
        variable.
        """
        self.fail_waiters('Variable purged.')

# Time, Constant variable types are now single-line implementations
Constant = lambda name, val: SimpleAttribute(name, lambda: val) #pylint: disable-msg=C0103,C0301,E0601
Time = lambda name: SimpleAttribute(name, time.asctime)         #pylint: disable-msg=C0103,C0301

class Barrier(BaseVar):
    """
    Variable type encapsulating the concept of group membership.  A client
    joins the group by storing any value into the variable.  It uses fetch to
    leave the group.

    XXX: If a client loses its connection without leaving the group, it
    corrupts the group.  Therefore, I need to add a mechanism that lets clients
    automatically leave the group when it loses its connection.  This might be
    implemented via the __client_disconnected method of the NwsService class,
    or perhaps only via the NwsProtocol class.
    """

    def __init__(self, name):
        """Create a new barrier variable.

          Arguments:
            name            - user-readable name for var
        """
        BaseVar.__init__(self, name)
        self._members = {}

    def __len__(self):
        # Keep this in sync with the __iter__ method.  Presently, always
        # returns 3.  When iterating over this variable, it will yield, in
        # order:
        #
        #  * number of members
        #  * list of members
        #  * number of members at barrier
        return 3

    def __iter__(self):
        # Keep __len__ in sync with this method.  Presently, always returns the
        # following 3 items in order:
        #
        #    * number of members
        #    * list of members
        #    * number of members at barrier
        members = ' '.join([str(m) for m in self._members])
        if not members:
            members = '<None>'

        def gen():
            """Helper generator function."""
            yield 'Number of members: %d' % len(self._members)
            yield 'List of members:   %s' % members
            yield 'Number at barrier: %d' % self.num_finders

        return gen()

    def store(self, client, value, metadata):
        #pylint: disable-msg=W0613
        """Handle a store request for a Barrier variable.

        The effect of this is to add the storing client to the group
        represented by this barrier.

          Arguments:
            client -- client performing the store
            value  -- value to store (unused)
        """
        num_members = len(self._members)
        assert self.num_finders == 0 or self.num_finders < num_members

        if client.transport.sessionno in self._members:
            # Client is trying to join the group a second time
            raise WorkspaceFailure('Client attempting to join barrier ' +
                                   'group, but is already a member')
        self._members[client.transport.sessionno] = 1

    def fetch(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Execute a fetch on this variable.  The effect of this
        is to remove the fetching client from the group represented
        by this Barrier.

          Arguments:
            client   -- client which is performing the fetch
            blocking -- is this a blocking fetch?
            val_index -- index of value to fetch
        """
        num_members = len(self._members)
        assert self.num_finders == 0 or self.num_finders < num_members

        try:
            del self._members[client.transport.sessionno]
        except (KeyError, AttributeError):
            raise WorkspaceFailure('Client has not joined this barrier group.')

        if self.num_finders >= len(self._members):
            consumed = self.new_value(0, str(num_members), {})
            assert not consumed

        return Response(value='')

    def find(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Execute a find on this variable.  The effect of this
        is to check if the fetching client is in the group represented
        by this Barrier.

          Arguments:
            client   -- client which is performing the find
            blocking -- is this a blocking find?
            val_index -- index of value to find
        """
        num_members = len(self._members)
        assert self.num_finders == 0 or self.num_finders < num_members

        if blocking:
            if client.transport.sessionno in self._members:
                if self.num_finders == num_members - 1:
                    response = Response(value=str(num_members))
                    consumed = self.new_value(0, response.value, {})
                    assert not consumed
                    return response
                else:
                    self.add_finder(client)
                    return None
            else:
                # return an error because they're not a member
                raise WorkspaceFailure('Client has not joined this barrier ' +
                                       'group.')
        else:
            return Response(value='%d out of %d at barrier' % 
                            (self.num_finders, num_members))

    def purge(self):
        """Handle a purge request on this variable."""
        self.fail_waiters('Variable purged.')

class Unknown(BaseVar):
    """Placeholder variable class for variables which have not been stored to
    yet.  An Unknown variable will exist from the time the first fetcher or
    finder accesses the variable until someone performs a or declares the
    variable, at which time, the appropriate variable type is substituted.
    """

    def __init__(self, name):
        """Create a new Unknown variable.

          Arguments:
            name            - user-readable name for var
        """
        BaseVar.__init__(self, name)

    def __len__(self):
        """Implementation of iterator protocol for Unknown-type variables."""
        return 0

    def __iter__(self):
        """Implementation of iterator protocol for Unknown-type variables."""
        return self

    def next(self):
        #pylint: disable-msg=R0201
        """Implementation of iterator protocol for Unknown-type variables."""
        raise StopIteration()

    def store(self, client, value, metadata):
        #pylint: disable-msg=R0201,W0613
        """Handle a store request for an Unknown variable.

        This is an error, and should never occur.

          Arguments:
            client -- client performing the store
            value  -- value to store (unused)
        """
        # this should never be called
        raise WorkspaceFailure('store called on a variable of unknown mode')

    def fetch(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a fetch request on this variable.

        For an Unknown variable, this always fails or blocks immediately.

          Arguments:
            client -- client for whom to perform fetch
            blocking -- is this a blocking fetch?
            val_index -- index of value to fetch (unused here)
        """
        if blocking:
            if _DEBUG:
                log.msg('queueing up blocking fetch request')
            self.add_fetcher(client)
            return None
        else:
            if _DEBUG:
                log.msg('returning unsuccessful reply')
            raise WorkspaceFailure('no value available')

    def find(self, client, blocking, val_index, metadata):
        #pylint: disable-msg=W0613
        """Handle a find request on this variable.

        For an Unknown variable, this always fails or blocks immediately.

          Arguments:
            client -- client for whom to perform find
            blocking -- is this a blocking find?
            val_index -- index of value to find (unused here)
        """
        if blocking:
            if _DEBUG:
                log.msg('queueing up blocking find request')
            self.add_finder(client)
            return None
        else:
            if _DEBUG:
                log.msg('returning unsuccessful reply')
            raise WorkspaceFailure('no value available')

    def purge(self):
        """Handle a purge request on this variable, causing all waiters to
        fail."""
        self.fail_waiters('Variable purged.')

CONTAINER_TYPES = {'fifo':      Fifo,
                   'lifo':      Lifo,
                   'single':    Single,
                   'multi':     Lifo,  # XXX: fix multi
                   '__time':    Time,
                   '__barrier': Barrier}

class Variable(object):
    """Class representing a variable in a workspace.  This class is a wrapper
    around the "container" class to hold the value (Single, Fifo, Lifo, etc.).
    """

    def __init__(self, var_name, hidden):
        """Initializer for a variable.

          Parameters:
            var_name        - variable name
            hidden          - should this var be hidden from the web UI?
        """
        self.__name = var_name
        self.__mode = 'unknown'
        self.__id = None
        self.__container = Unknown(self.__name)
        self.__hidden = hidden

    def __str__(self):
        return 'Variable[%s]' % self.__name

    def __get_var_id(self):
        """Get the unique 'id' for this variable."""
        return self.__id

    def __set_var_id(self, var_id):
        """Set the unique 'id' for this variable."""
        self.__id = var_id
        self.__container.vid = var_id
    vid = property(__get_var_id, __set_var_id)

    def get_name(self):
        """Get the variable name for this variable."""
        return self.__name
    name = property(get_name)

    def __get_hidden(self):
        """Hide this variable from the Web UI?"""
        return self.__hidden
    hidden = property(__get_hidden)

    # called from the web interface
    def mode(self):
        """Get the mode of this variable."""
        return self.__mode

    # called from the web interface
    def values(self):
        """Get the container of the values in this variable."""
        # this must return an iterable
        return self.__container

    def __get_num_fetchers(self):
        """Get the count of fetchers in this variable."""
        return self.__container.num_fetchers
    num_fetchers = property(__get_num_fetchers)

    def __get_num_finders(self):
        """Get the count of finders in this variable."""
        return self.__container.num_finders
    num_finders = property(__get_num_finders)

    def __get_num_values(self):
        """Get the count of values in this variable."""
        return len(self.__container)
    num_values = property(__get_num_values)

    def set_mode(self, mode):
        """Set the mode of this variable.  This is called when a variable is
        declared.  It sets the type of container used for the variable.

          Parameters:
            mode -- the variable mode (for instance, 'single', 'lifo', 'fifo')
        """
        if _DEBUG:
            log.msg('set_mode(%s, %s)' % (str(self), mode))
        if self.__mode == 'unknown':
            finders  = self.__container.finders
            fetchers = self.__container.fetchers
            try:
                cont_type = CONTAINER_TYPES[mode]
                self.__container = cont_type(self.__name)
                self.__container.vid = self.vid
                self.__container.finders = finders
                self.__container.fetchers = fetchers
                self.__mode = mode
                if _DEBUG:
                    log.msg('set_mode(%s, %s): new container type = %s' %
                            (str(self), mode, str(type(self.__container))))
            except KeyError:
                raise BadModeException("illegal mode specified")
        elif self.__mode != mode:
            raise BadModeException("mode is already set to incompatible value")

    def set_container(self, cont):
        """Specialized version of set_mode to be used from plugins to create
        variables using custom container classes."""
        self.__mode = 'custom'
        self.__container = cont

    def new_value(self, val_index, val, metadata):
        """Publish a new value to the appropriate waiters."""
        self.__container.new_value(val_index, val, metadata)

    def purge(self):
        """Purge this variable from the workspace."""
        self.__container.purge()

    def format(self):
        """Format this variable for the 'list vars' command."""
        return '%s\t%d\t%d\t%d\t%s' % (self.name, len(self.__container),
                self.__container.num_fetchers,
                self.__container.num_finders,
                self.__mode)

    def store(self, client, val, metadata):
        """Set the value of this variable, converting it to FIFO type if it is
        Unknown.

          Arguments:
            client -- client for whom to store
            val    -- value to store
        """
        if self.__mode == 'unknown':
            self.set_mode('fifo')
        self.__container.store(client, val, metadata)

    def fetch(self, client, is_blocking, val_index, metadata):
        """Do a fetch operation on this variable.

          Arguments:
            client          - client for whom to fetch/find
            is_blocking     - is this a blocking operation?
            val_index       - value index, if this is an iterated operation
            metadata        - metadata, if any
        """
        return self.__container.fetch(client, is_blocking, val_index, metadata)

    def find(self, client, is_blocking, val_index, metadata):
        """Do a find operation on this variable.

          Arguments:
            client          - client for whom to fetch/find
            is_blocking     - is this a blocking operation?
            val_index       - value index, if this is an iterated operation
            metadata        - metadata, if any
        """
        return self.__container.find(client, is_blocking, val_index, metadata)

