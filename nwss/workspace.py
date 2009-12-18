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
Core NetWorkSpaces server - workspace implementation.
"""

from __future__ import generators
from random import randint
from twisted.internet import reactor, defer, task
from twisted.python import log

from nwss.base import ServerException, NoSuchVariableException
from nwss.base import WorkspaceFailure
from nwss.base import Response
from nwss.stdvars import Variable, BaseVar
import nwss

_DEBUG = nwss.config.is_debug_enabled('NWS:workspace')

class OperationFailure(ServerException):
    """Used to signal the failure of an operation inside a plugin and
    communicate back an error message to the user.
    """
    def __init__(self, message, code=1):
        ServerException.__init__(self, message)
        self.return_code = code

def call_after_delay(delay, func, *args, **kw):
    """Utility to schedule a particular call to happen at a specific point in
    the future.  Utility for plugin development.

      Parameters:
          delay         - delay before call (in seconds)
          func          - function to call
          ...           - arguments to function
    """
    deferred = defer.Deferred()
    deferred.addCallback(lambda ignored: func(*args, **kw)) #pylint: disable-msg=W0142,C0301
    reactor.callLater(delay, deferred.callback, None)       #pylint: disable-msg=E1101,C0301

class WorkSpace(object):
    #pylint: disable-msg=R0902
    """Server-side object representing a workspace in the NetWorkSpace
    server."""

    def __init__(self, name):
        """Initializer for a WorkSpace object.

          Parameters:
            name            - name for workspace
        """
        self.__bindings = {}        # str (name) -> Variable
        self.__vars_by_id = {}      # str (id)   -> Variable
        self.name = name
        self.owner = ''
        self.persistent = False
        self.__periodic_tasks = []
        self.__have_hidden = False

    def __is_owned(self):
        """Synthetic 'owned' attribute."""
        return (self.owner != '')
    owned = property(__is_owned)

    def __str__(self):
        return 'WorkSpace[%s]' % self.name

    ###############################################################
    # Private interface exposed to NwsService
    ###############################################################

    def _started(self, metadata):
        """Callback indicating that this workspace has been created and is
        active.
        """
        self.__hook('created_ws', metadata)

    def _stopped(self):
        """Callback indicating that this workspace has been shutdown and will
        be destroyed.
        """
        for periodic_task in self.__periodic_tasks:
            periodic_task.stop()
        self.__hook('destroyed_ws')

    def _declare_var(self, name, mode, metadata):
        #pylint: disable-msg=W0613
        """Declare a variable to be of a particular mode.  Currently defined
        modes are 'lifo', 'fifo', 'single', '__time', and '__barrier'.

        Parameters:
            name            - name of the variable
            mode            - 'fifo', 'lifo', etc.
            metadata        - metadata passed in from the client
        """
        var = self.__get_var_object(name)
        var.set_mode(mode)

    def _fetch_var(self, name, client, is_blocking, iterstate, metadata):
        #pylint: disable-msg=R0913
        """Fetch a value from a variable.  This encompasses all of the
        different {,i}fetch{Try,} variants of the operation.

          Parameters:
            name            - name of the variable
            client          - protocol object from whom request originated
            is_blocking     - True if blocking, False if a *Try variant
            iterstate       - iteration state - ('', -1) for non-iterated
            metadata        - metadata passed in from the client
        """
        var = self.__get_var_object(name)

        # Check for variable id mismatch on an iterated op
        if iterstate[0]:
            if iterstate[0] != var.vid:
                raise WorkspaceFailure('Variable id mismatch.')

        # Run the initial hook
        self.__hook('fetch_pre', var, iterstate[1], is_blocking, metadata)

        # Fetch the next value, if possible
        response = var.fetch(client, is_blocking, iterstate[1], metadata)
        if response is None:
            return None

        # Stash the iter state if the variable hasn't written its own
        if response.iterstate is None:
            response.iterstate = var.vid, max(0, iterstate[1])
        return response

    def _find_var(self, name, client, is_blocking, iterstate, metadata):
        #pylint: disable-msg=R0913
        """Find a value from a variable.  This encompasses all of the different
        {,i}find{Try,} variants of the operation.

          Parameters:
            name            - name of the variable
            client          - protocol object from whom request originated
            is_blocking     - True if blocking, False if a *Try variant
            iterstate       - iteration state - ('', -1) for non-iterated
            metadata        - metadata passed in from the client
        """
        var = self.__get_var_object(name)

        # Check for variable id mismatch on an iterated op
        if iterstate[0]:
            if iterstate[0] != var.vid:
                raise WorkspaceFailure('Variable id mismatch.')

        # Run the initial hook
        self.__hook('find_pre', var, iterstate[1], is_blocking, metadata)

        # Find the value, if possible
        response = var.find(client, is_blocking, iterstate[1], metadata)
        if response is None:
            return None

        # Stash the iter state if the variable hasn't written its own
        if response.iterstate is None:
            response.iterstate = var.vid, max(0, iterstate[1])
        return response

    def _set_var(self, name, client, val, metadata):
        """Store a value into a variable.

          Parameters:
            name            - name of the variable
            client          - protocol object from whom request originated
            val             - value to store
            metadata        - metadata passed in from the client
        """
        var = self.__get_var_object(name)
        self.__hook('store_pre', var, val, metadata)
        var.store(client, val, metadata)
        self.__hook('store_post', var, val, metadata)

    def _delete_var(self, name, metadata):
        """Delete a variable.

        Parameters:
            name            - name of the variable
            metadata        - metadata passed in from the client
        """
        self.__hook('delete_pre', name, metadata)
        self.__delete_var_object(name)
        self.__hook('delete_post', name, metadata)
        return 0

    def _get_bindings(self, hide=False):
        """Get the set of all variable bindings in this workspace.

          Parameters:
            hide            - do we exclude 'hidden' bindings?
        """
        if hide  and  not self.__have_hidden:
            hide = False
        if not hide:
            return self.__bindings
        else:
            bindings = {}
            for key, value in self.__bindings.items():
                if not value.hidden:
                    bindings[key] = value
            return bindings

    def _get_binding(self, name, hide=False):
        """Get a particular variable binding.

          Parameters:
            name            - name of the variable
            hide            - do we exclude 'hidden' bindings?
        """
        var = self.__bindings[name]
        if hide and var.hidden:
            return None
        return var

    def _set_owner_info(self, owner, persistent, metadata):
        """Set the ownership of this workspace if it isn't owned yet.

        If the workspace is unowned, it will take on the owner and persistence
        properties of whichever client caused this to be called.  This is
        called when someone opens a workspace that they are willing to assert
        ownership of, if the workspace exists and noone has previously asserted
        ownership of the space.

          Parameters:
            owner           - owner of client for whom this method is called
            persistent      - request the space to be persistent
        """
        status = False
        if not self.owned:
            self.__hook('setowner_pre', owner, persistent, metadata)
            self.owner = owner
            self.persistent = persistent
            status = True
            self.__hook('setowner_post', owner, persistent, metadata)
        return status


    ###############################################################
    # Private implementation
    ###############################################################

    def __has_hook(self, name):
        """Check for a named hook function.

          Parameters:
            name            - hook name
        """
        hookname = 'hook_' + name
        return hasattr(self, hookname)

    def __hook(self, name, *args):
        """Call a named hook function.

          Parameters:
            name            - hook name
            args            - arguments to pass to hook
        """
        hookname = 'hook_' + name
        if hasattr(self, hookname):
            hook = getattr(self, hookname)
            return hook(*args)
        return None

    def __allocate_var_id(self):
        """Allocate a unique id for a variable."""
        for _ in range(1000):
            new_id = '%020u' % randint(0, 999999999)
            if new_id not in self.__vars_by_id:
                return new_id
        else:
            raise ServerException('Internal error: Failed to allocate a ' +
                                  'unique variable id.')

    def __get_var_object(self, name, create=True):
        """Get and/or create a variable in this workspace.

        If the variable has not been created and 'create' is true, it will be created
        as a simple variable.

          Parameters:
            name            - name of variable
            create          - flag indicating whether the variable may be created
        """
        try:
            var = self.__bindings[name]
        except KeyError:
            if not create:
                var = None
            else:
                var = Variable(name, False)
                self.add_variable(var)
        return var

    def __delete_var_object(self, name):
        """Remove a variable from this workspace.

          Parameters:
            name            - name of variable
        """
        if not self.remove_variable(name):
            raise NoSuchVariableException('no variable named %s' % name)

    ###############################################################
    # Interface exposed to plugin classes
    ###############################################################

    def call_hook(self, name, *args):
        """Interface to allow plugins to use the same 'hook' mechanism as the
        base workspace.

          Parameters:
              name          - hook name (method will be hook_<name>)
              args          - args to pass to hook
        """
        return self.__hook(name, *args)

    def add_periodic_task(self, period, periodic_task):
        """Add a periodic task to this workspace which will be called every
        'period' seconds.  This is intended for use by the plugins.

          Parameters:
              period        - periodicity of task in seconds
              periodic_task - 0-args function to call periodically
        """
        call = task.LoopingCall(periodic_task)
        self.__periodic_tasks.append(call)
        call.start(period)

    def create_standard_var(self, varname, mode, hidden=True):
        """Utility to simplify the creation of standard variables.

          Parameters:
              varname       - name of variable
              mode          - variable mode
              hidden        - should the var be hidden from the web UI?
        """
        var = Variable(varname, hidden)
        var.set_mode(mode)
        self.add_variable(var)

    def create_var(self, container, hidden=False):
        """Utility to simplify the creation of custom variable types.

          Parameters:
              container     - custom container for variable
              hidden        - should the var be hidden from the web UI?
        """
        var = Variable(container.name, hidden)
        var.set_container(container)
        self.add_variable(var)

    def add_variable(self, var):
        """Add a new variable to this workspace, setting its unique ID and
        adding it to all appropriate indices.

          Parameters:
              var           - variable to add
        """
        var_id = self.__allocate_var_id()
        var.vid = var_id
        self.__vars_by_id[var_id] = var
        self.__bindings[var.name] = var
        if var.hidden:
            self.__have_hidden = True

    def remove_variable(self, name):
        """Remove a variable from this workspace by name.

          Parameters:
              name          - variable name to remove
        """
        try:
            return self.remove_variable_by_id(self.__bindings[name].vid)
        except KeyError:
            return False

    def remove_variable_by_id(self, var_id):
        """Remove a variable from this workspace by unique id.

          Parameters:
              var_id        - variable id to remove
        """
        try:
            var = self.__vars_by_id.pop(var_id)
            var.purge()
            try:
                del self.__bindings[var.name]
            except KeyError:
                pass
            return True
        except KeyError:
            return False

    def get_variable(self, name):
        """Fetch a variable from this workspace by name.

          Parameters:
              name          - variable name to fetch
        """
        return self.__bindings.get(name)

    def get_variable_by_id(self, var_id):
        """Fetch a variable from this workspace by unique id.

          Parameters:
              var_id        - variable id to fetch
        """
        return self.__vars_by_id.get(var_id)

    def purge(self, metadata=None):
        """Purge all variables in this workspace.

          Parameters:
            metadata        - metadata passed in from the client
        """
        if metadata is None:
            metadata = {}
        self.__hook('purge_pre', metadata)
        names = self.__bindings.keys()
        for name in names:
            var = self.__bindings.pop(name)
            var.purge()
        self.__vars_by_id.clear()
        self.__hook('purge_post', metadata)

class GetRequest(object):
    #pylint: disable-msg=R0903
    """Encapsulation of a fetch/find request used by the simplified plugin
    system.
    """

    def __init__(self, name, metadata):
        self.name      = name
        self.blocking  = True
        self.remove    = True
        self.iterstate = None
        self.metadata  = metadata

class SetRequest(object):
    #pylint: disable-msg=R0903
    """Encapsulation of a store request used by the simplified plugin
    system.
    """

    def __init__(self, name, value, metadata):
        self.name      = name
        self.value     = value
        self.metadata  = metadata

def constant_fail(message, status=1):
    """Utility to create functions which fail with a custom message and status
    code.  Useful for plugins.
    """

    def handler(*args):
        #pylint: disable-msg=W0613
        """Generic exception-thrower."""
        raise WorkspaceFailure(message, status)
    return handler

def constant_return(value):
    """Utility to create functions which return a constant value.  Useful for
    writing plugins.
    """

    def handler(*args):
        #pylint: disable-msg=W0613
        """Generic constant function."""
        return value
    return handler

def function_return(func):
    """Utility to create functions which return a value from a no-args function
    call.  Useful for writing plugins.
    """
    def handler(*args):
        #pylint: disable-msg=W0613
        """Generic 0-arg function caller."""
        return func()
    return handler

def singleton_iter_provider(func):
    """Utility to implement iteration functionality on a new style plugin
    variable.
    """
    def handler(*args):
        #pylint: disable-msg=W0613
        """Generic singleton iterator functionality."""
        val = func()
        if val is None:
            return [], 0
        else:
            return [val], 1
    return handler

class MetaVariable(BaseVar):
    """Utility variable "container" type to simplify implementation of custom
    variables in workspace plugins.
    """

    def __init__(self, name, get_handler, iter_provider=None, cb_handler=None):
        BaseVar.__init__(self, name)
        self.get_handler  = get_handler
        if iter_provider is None:
            self.iter_handler = constant_return(([], 0))
        else:
            self.iter_handler = iter_provider
        if cb_handler is None:
            self.cb_handler   = constant_return(False)
        else:
            self.cb_handler   = cb_handler
        self.set_handler  = constant_fail('Store is not supported for this ' +
                                          'variable.')
        self.unwrap_stores = True

    def __len__(self):
        _, count = self.iter_handler()
        return count

    def __iter__(self):
        iterable, _ = self.iter_handler()
        return iter(iterable)

    def store(self, client, value, metadata):
        """Handle a store request for a metavariable."""
        if self.unwrap_stores:
            request = SetRequest(self.name, value.val(), metadata)
        else:
            request = SetRequest(self.name, value, metadata)
        self.set_handler(client, request)

    def __value_callback(self, client, request, value):
        """Callback to announce the unblocking of a fetch/find operation."""
        if request.remove:
            try:
                self.fetchers.remove(client)
            except ValueError:
                log.msg('Blocking fetcher was not in the fetchers list for '
                            + self.name)
                return
        else:
            try:
                self.finders.remove(client)
            except ValueError:
                log.msg('Blocking finder was not in the finders list for '
                            + self.name)
                return

        if isinstance(value, OperationFailure):
            client.send_error(value.args[0], value.return_code, True)
            return

        if not isinstance(value, Response):
            data = str(value.value)
            metadata = value.metadata
            if request.iterstate is None:
                val_index = 0
            else:
                val_index = request.iterstate[1]
            value = Response(metadata, data)
            value.iterstate = self.vid, val_index

        client.send_long_response(value)

    def __handle_get(self, client, request):
        """Generic fetch/find implementation."""
        try:
            value = self.get_handler(client, request)
            if value is not None:
                if not isinstance(value, Response):
                    value = Response(value=value)
                if request.iterstate is not None:
                    val_index = request.iterstate[1] + 1
                    value.iterstate = request.iterstate[0], val_index
                return value
            elif not request.blocking:
                raise OperationFailure('no value available.')
            else:
                thunk = lambda val: self.__value_callback(client, request, val)
                if request.remove:
                    self.add_fetcher(client)
                else:
                    self.add_finder(client)
                if not self.cb_handler(client, request, thunk):
                    raise OperationFailure(
                            'Metavariable did not add callback.')
                else:
                    return None
        except OperationFailure, fail:
            if fail.return_code == 0:
                fail.return_code = 1
            raise WorkspaceFailure(fail.args[0], fail.return_code)

    def fetch(self, client, blocking, val_index, metadata):
        """Fetch implementation for metavariables."""
        request = GetRequest(self.name, metadata)
        request.blocking = blocking
        request.remove   = True
        if val_index is not None:
            request.iterstate = (self.vid, val_index)
        return self.__handle_get(client, request)

    def find(self, client, blocking, val_index, metadata):
        """Find implementation for metavariables."""
        request = GetRequest(self.name, metadata)
        request.blocking = blocking
        request.remove   = False
        if val_index is not None:
            request.iterstate = (self.vid, val_index)
        return self.__handle_get(client, request)

    def purge(self):
        """Purge this variable from the workspace, causing any clients waiting
        for a value to fail.
        """
        self.fail_waiters('Variable purged.')

def simple_metavariable(name, func):
    """Utility to create a simple metavariable which does not accept store
    requests, on which fetch and find always succeed, and on which the value
    returned from a fetch/find is taken from a 0-arg function.
    """
    return MetaVariable(name,
                        function_return(func),
                        singleton_iter_provider(func))

