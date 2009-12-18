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
Core NetWorkSpaces server - common bits.
"""

import os, mmap, traceback

from twisted.python import log

# bit codings for the descriptor.
DIRECT_STRING = 1

class ServerException(Exception):
    """Base class for all exceptions raised by this module."""

    def __str__(self):
        #pylint: disable-msg=W0141
        return '%s[%s]' % (self.__class__.__name__,
                ' '.join(map(str, self.args)))

    def __repr__(self):
        #pylint: disable-msg=W0141
        return '%s(%s)' % (self.__class__.__name__,
                ', '.join(map(repr, self.args)))

class WorkspaceFailure(ServerException):
    """Exception thrown by Workspace to signal that a normal (i.e. user-level)
    error has occurred during the operation.
    """

    def __init__(self, msg, status=1):
        ServerException.__init__(self, msg)
        self.status = status

class BadModeException(ServerException):
    """Variable cannot be set to specified mode."""

class NoSuchVariableException(ServerException):
    """No variable by specified name."""

class Response(object):
    #pylint: disable-msg=R0903
    """Response from the server to the client."""

    def __init__(self, metadata=None, value=None):
        self.status    = 0
        if metadata is None:
            metadata = {}
        self.metadata  = metadata
        self.value     = value
        self.iterstate = None

class Value(object):
    """Value wrapper class handling out-of-band transmission of long data."""

    def __init__(self, desc, val):
        """Initialize a value object.

          Arguments:
            desc            - type descriptor for object
            val             - either a string or a (filename, length) tuple
        """
        self.__type_descriptor = desc
        self._val = val
        self._consumed = False

        if isinstance(val, str):
            self._long = False
            self._length = len(val)
        else:
            # if it's not a string, assume it's a tuple: (filename, length)
            self._long = True
            self._length = val[1]

    def consumed(self):
        """Flag this value as consumed.
        """
        self._consumed = True

    def access_complete(self):
        """Notify this value that it has been sent to the client, and should
        now deallocate its file if it has been consumed.
        """
        if self._consumed:
            self.close()

    def close(self):
        """Deallocate any resources associated with this value."""
        if self._long:
            try:
                os.remove(self._val[0])
            except OSError:
                log.msg('error removing file %s' % self._val[0])
                traceback.print_exc()

    def get_file(self):
        """Memory map the file associated with this long value.  If this is not
        a long value, this method will fail.
        """
        assert self._long, 'get_file illegally called on string value'
        datafile = open(self._val[0], 'rb')
        memory = mmap.mmap(datafile.fileno(), self._length,
                           access=mmap.ACCESS_READ)
        datafile.close()
        return memory

    def is_large(self):
        """Is this a large value?"""
        return self._long

    def __get_type_descriptor(self):
        """Get the type descriptor for this value."""
        return self.__type_descriptor
    type_descriptor = property(__get_type_descriptor)

    def val(self):
        """Get the raw value for this non-long value.

        If this is a long value, this method will fail."""
        assert not self._long, 'val illegally called on long value'
        return self._val

    def set_val(self, data):
        """Set the raw value for this non-long value.

        If this is a long value, this method will fail."""
        assert not self._long, 'val illegally called on long value'
        self._val = data

    def length(self):
        """Get the length of this value in bytes."""
        return self._length

ERROR_VALUE = Value(0, '')
