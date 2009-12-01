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

# server for NetWorkSpaces.

"""
Core NetWorkSpaces server.
"""

import os, traceback

from tempfile import mkstemp
from twisted.internet import protocol
from twisted.python import log

from nwss.protocol import NwsProtocol
from nwss.protoutils import WsTracker, WsNameMap
try:
    from nwss.web import NwsWeb
except ImportError:
    # Disable web interface -- couldn't load nwss.web
    NwsWeb = None   #pylint: disable-msg=C0103

from nwss.base import BadModeException
from nwss.base import NoSuchVariableException
from nwss.base import WorkspaceFailure
from nwss.base import Value
from nwss.base import Response
from nwss.workspace import WorkSpace
import nwss

_DEBUG = nwss.config.is_debug_enabled('NWS:server')

def var_list_csv(bindings):
    """Produce a variable list from the given dictionary of bindings.

      Arguments:
        bindings -- the dictionary
    """
    k = bindings.keys()
    k.sort()
    return ','.join(k)

def get_int_ws_name(client, ext_name, long_reply):
    """Get the internal name for a workspace.

      Arguments:
        client     - the client state in which to look up the name
        ext_name   - the user-visible workspace name to look up
        long_reply - send a long reply in case of an error?
    """
    int_name = client.workspace_names.get(ext_name)
    if int_name is None:
        client.send_error('Workspace %s has not been opened.' % ext_name,
                          2001, long_reply)
    return int_name

def plugin_score_function(plug):
    """Plugins are ordered by their PRIORITY class fields, with an omitted
    priority counting as a 0."""
    if hasattr(plug, 'PRIORITY'):
        return plug.PRIORITY
    else:
        return 0

def find_best_plugin(plugins):
    """Order the list of plugins by the scoring metric specified by the
    plugin_score_function.  Technically, we aren't ordering the list, but
    simply selecting the best item."""
    best_pri = None
    best_plugin = None
    for plugin in plugins:
        pri = plugin_score_function(plugin)
        if best_pri is None or pri > best_pri:
            best_plugin = plugin
            best_pri  = pri
    return best_plugin

PLUGINS_ENABLED = True
try:
    from pkg_resources import Environment, working_set
except ImportError:
    PLUGINS_ENABLED = False

ALL_PLUGINS = None
def load_plugin(name):
    """Plugin loader.  This is responsible for interfacing to the EGG loader
    and finding the best plugin for a given plugin type."""
    if not PLUGINS_ENABLED:
        log.msg('Plugin requested, but pkg_resources is not installed.')

        # Replace the body of this function so we don't get a lot of noise.
        dummy_load_plugin = lambda name: None
        #pylint: disable-msg=W0612
        load_plugin.func_code = dummy_load_plugin.func_code
        return None

    if _DEBUG:
        log.msg('Loading plugin "%s"' % name)
    global ALL_PLUGINS      #pylint: disable-msg=W0603
    if ALL_PLUGINS is None:
        if _DEBUG:
            log.msg('Scanning plugin dirs')
        ALL_PLUGINS = working_set
        for i in nwss.config.nwsPluginDirs:
            if _DEBUG:
                log.msg('Scanning plugin dir "%s"' % i)
            ALL_PLUGINS.add_entry(i)
        env = Environment(nwss.config.nwsPluginDirs)
        ALL_PLUGINS.require(*[i for i in env])
    entry_points = ALL_PLUGINS.iter_entry_points('nws.workspace', name)
    plugins = [i.load() for i in entry_points]
    if _DEBUG:
        log.msg('Found %d matching plugins' % len(plugins))
    if len(plugins) == 0:
        log.msg('Request for plugin type "%s" found no plugins' % name)
        return None
    return find_best_plugin(plugins)

def create_space(ext_name, metadata):
    """Create a workspace object with the given name, and metadata.

      Parameters:
          ext_name          - name for the new space
          metadata          - metadata to control space creation
    """
    if _DEBUG:
        log.msg('metadata = ' + str(metadata))

    # Find the right constructor
    if metadata.has_key('wstype'):
        ws_type = metadata['wstype']
        log.msg('Creating plugin workspace type "%s" (name "%s")' %
                    (ws_type, ext_name))
        ctor = load_plugin(ws_type)
        if ctor is None:
            log.msg("ERROR: Failed to create workspace - " +
                            "couldn't load plugin.")
            raise WorkspaceFailure("Failed to create workspace: " +
                                   "couldn't load plugin.")
    else:
        log.msg('Creating standard workspace (name "%s")' % ext_name)
        ctor = WorkSpace

    # Create the space
    space = ctor(ext_name)
    space._started(metadata)    #pylint: disable-msg=W0212
    return space


class NwsService(protocol.ServerFactory):
    #pylint: disable-msg=W0212
    """The NWS Service itself, in suitable form to attach to a Twisted server.
    """

    def __init__(self):
        """Initialize an NWS service."""

        # keep a list of the protocol objects that we've created
        self.protocols = {}
        self.__protokey = 0

        self.__tmp_filename = None
        self.ws_basename = None

        # Create default space
        default_ext_name = '__default'
        default_space = WorkSpace(default_ext_name)
        default_space._set_owner_info('[system]', True, None)
        default_int_name = default_ext_name, 0
        default_space.internal_name = default_int_name

        self.__ext_to_int_ws_name = {
                default_ext_name : default_int_name
        }
        self.spaces = {
                default_int_name : default_space
        }

        self.__ws_counter = 1

    ####################################################
    # Twisted interface
    ####################################################

    # Twisted uses this to determine which protocol handler to instantiate
    protocol = NwsProtocol

    def buildProtocol(self, addr):
        #pylint: disable-msg=C0103
        """Build a protocol object for a NWS connection.  This is called from
        the Twisted framework and expects us to return a newly created protocol
        object.

          Arguments:
            addr -- address of remote side
        """
        proto = protocol.Factory.buildProtocol(self, addr)
        proto.protokey = self.__protokey
        self.protocols[proto.protokey] = proto
        self.__protokey += 1
        if _DEBUG:
            log.msg('built a new protocol[%d]: %s' %
                    (proto.protokey, str(self.protocols)))

        proto.owned_workspaces = WsTracker()
        proto.workspace_names  = WsNameMap()

        return proto

    def startFactory(self):
        #pylint: disable-msg=C0103
        """Callback when this factory is started."""

        log.msg('NetWorkSpaces Server version %s' % nwss.__version__)
        if NwsWeb is None:
            log.msg('WARNING: The web interface is not available, '
                    'probably because twisted.web is not installed')
        tmpdir = nwss.config.nwsTmpDir
        log.msg('using temp directory ' + tmpdir)
        # XXX: Why do we create this temp file?  Creating a unique random
        #      workspace name can be done more easily without resorting to
        #      this.
        tmpfile, self.__tmp_filename = mkstemp(prefix='__nwss', dir=tmpdir)
        self.ws_basename = os.path.basename(self.__tmp_filename)
        try:
            os.close(tmpfile)
        except OSError:
            pass

    def stopFactory(self):
        #pylint: disable-msg=C0103
        """Callback when this factory is stopped."""

        log.msg('stopping NwsService')
        try:
            os.remove(self.__tmp_filename)
        except OSError:
            pass

        # purge all WorkSpace objects, which will remove the temp files
        # currently in use
        for int_name, space in self.spaces.items():
            try:
                space.purge()
                space._stopped()
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception:
                #pylint: disable-msg=W0703
                log.msg("error while purging workspace %s" % int_name[0])
                traceback.print_exc()

        log.msg('stopping complete')

    ####################################################
    # Interface to web UI
    ####################################################

    def get_ext_to_int_mapping(self):
        """Get the external-to-internal name mapping for all current
        workspaces."""
        return self.__ext_to_int_ws_name

    ####################################################
    # Mechanics of workspace creation/destruction
    ####################################################

    def __reference_space(self, ext_name, client, can_create, metadata):
        """Reference a workspace, causing it to spring into existence if it
        does not exist and the client is willing to create the workspace.

          Arguments:
            ext_name        - the workspace name
            client          - client connection
            can_create      - can we create the workspace?
            metadata        - metadata to use for space creation
        """
        if metadata is None:
            metadata = {}
        if not self.__ext_to_int_ws_name.has_key(ext_name):
            # return an error if the workspace shouldn't be created
            if not can_create:
                return None

            # we use a separate internal name that allows us to track
            # instances. e.g., workspace 'foo' is created, deleted and created
            # again. a connection using the first may map 'foo' to the internal
            # "name" the tuple '(foo, 1)' while a connection using the second
            # may map 'foo' to '(foo, 7)'.  Here, we build the internal name.
            int_name = (ext_name, self.__ws_counter)
            self.__ws_counter += 1

            # Create the workspace
            space = create_space(ext_name, metadata)
            space.internal_name = int_name

            # Store the space in a two-level lookup:
            #   ext_name -> int_name -> space
            self.spaces[int_name] = space
            self.__ext_to_int_ws_name[ext_name] = int_name
        else:
            # Look up the space in a two-level lookup:
            #   ext_name -> int_name -> space
            int_name = self.__ext_to_int_ws_name[ext_name]
            space = self.spaces[int_name]

        # Debug mode only: Check for and log the case where the client had an
        # out of date external -> internal mapping for the workspace name.
        if _DEBUG:
            old_int_name = client.workspace_names.get(ext_name)
            if old_int_name is not None and old_int_name != int_name:
                log.msg('connection has new reference (%s, %s)' %
                        (old_int_name, int_name))

        # Update the client's external -> internal name mapping
        client.workspace_names.set(ext_name, int_name)
        return space

    def goodbye(self, client):
        """Signal the closure of a given client connection.

          Arguments:
            client          - client connection
        """
        self.__client_disconnected(client)

    # this method is called by the NwsProtocol object when
    # it loses it's connection
    def __client_disconnected(self, client):
        """Handle the closure (intentional or accidental) of a client
        connection.

          Arguments:
            client          - client connection
        """
        self.__purge_workspaces_for_client(client)
        if client.blocking:
            client.remove_from_waiter_list()
        try:
            del client.factory.protocols[client.protokey]
            if _DEBUG:
                log.msg("after removing protocol: " +
                        str(client.factory.protocols))
        except KeyError:
            log.msg("Internal error: Protocol lost connection, " +
                    "but was not in the connection map.")
            traceback.print_exc()

    def __purge_workspaces_for_client(self, client):
        """Purge all workspaces opened by a given client connection.

          Arguments:
            client          -- client connection
        """
        if _DEBUG:
            log.msg('purging owned workspaces')
        for int_name in client.owned_workspaces.as_list():
            if _DEBUG:
                log.msg('purging %s' % str(int_name[0]))
            try:
                if not self.spaces[int_name].persistent:
                    space = self.spaces.pop(int_name)
                    space.purge({})
                    space._stopped()
                    try:
                        self.__ext_to_int_ws_name.pop(int_name[0])
                    except KeyError:
                        log.msg('WARNING: workspace name "%s" is not known',
                                int_name[0])
            except KeyError:
                log.msg('workspace no longer exists: %s' % str(int_name))
            except Exception:
                log.msg("unexpected error while purging client's workspaces")
                traceback.print_exc()

        client.owned_workspaces.clear()

    ####################################################
    # Mechanics of command dispatch
    ####################################################

    def __find_workspace(self, client, ext_name, long_reply=False):
        """Look up a given workspace, or produce an error.

          Arguments:
            client      - client connection for whom to access the workspace
            ext_name    - user-visible workspace name
            long_reply  - send a long reply in case of an error?
        """
        int_name = get_int_ws_name(client, ext_name, long_reply)
        if int_name is None:
            return None

        try:
            workspace = self.spaces[int_name]
        except KeyError:
            # this probably means the workspace was deleted by another client
            client.send_error('No such workspace.', 100, long_reply)
            return None

        return workspace

    def handle_command(self, client, metadata, *args):
        """Perform the requested workspace operation.

          Arguments:
            client -- client connection, prepopulated with the requested workspace operation
        """
        # dispatch
        try:
            self.OPERATIONS[args[0]](self,
                                     client,
                                     metadata=dict(metadata),
                                     *args)
        except KeyError:
            client.send_error('Unknown verb "%s"' % args[0])
        except Exception:
            log.msg('ignoring unexpected exception')
            log.msg('protocol arguments: ' + str(args))
            traceback.print_exc()

    ####### Command handler: "declare var"
    def cmd_declare_var(self, client, op_name, ext_name, var_name, mode,
                        metadata=None):
        #pylint: disable-msg=W0613,R0913
        """NWS Command handler: Declare a variable, creating it if it did not
        exist, or setting its mode if it was formerly unknown.

          Arguments:
            client          - client connection
            op_name         - operation name (unused here)
            ext_name        - the workspace name
            var_name        - the variable name to declare
            mode            - the mode for the created variable
        """
        # convert null metadata to empty metadata
        if metadata is None:
            metadata = {}

        # find the workspace
        workspace = self.__find_workspace(client, ext_name)
        if workspace is None:
            return

        # declare the variable
        try:
            workspace._declare_var(var_name, mode, metadata)
            client.send_short_response()
        except BadModeException:
            client.send_error('Cannot change variable mode to "%s".' % mode)
        except Exception, exc:
            client.send_error('Internal error: "%s".' % str(exc), 2000)
            raise

    ####### Command handler: "delete ws"
    def cmd_delete_workspace(self, client, op_name, ext_name, metadata=None):
        #pylint: disable-msg=W0613
        """NWS Command handler: Delete the workspace.

          Arguments:
            client          - client connection
            op_name         - operation name (unused here)
            ext_name        - the workspace name
        """
        # convert null metadata to empty metadata
        if metadata is None:
            metadata = {}

        # delete the workspace
        try:
            int_name = self.__ext_to_int_ws_name.pop(ext_name)
            space = self.spaces.pop(int_name)
            space.purge(metadata)
            space._stopped()
            client.workspace_names.remove(ext_name)
            client.owned_workspaces.remove(int_name)
            client.send_short_response()
        except KeyError:
            log.msg('workspace "%s" does not exist.' % ext_name)
            client.send_error('Workspace "%s" does not exist.' % ext_name)
        except Exception, exc:
            client.send_error('Internal error: "%s".' % str(exc), 2000)
            raise

    ####### Command handler: "delete var"
    def cmd_delete_var(self, client, op_name, ext_name, var_name,
                       metadata=None):
        #pylint: disable-msg=W0613,R0913
        """NWS Command handler: Delete the variable.

          Arguments:
            client          - client connection
            op_name         - operation name (unused here)
            ext_name        - the workspace name
            var_name        - the variable name
            metadata        - metadata for this operation
        """
        # convert null metadata to empty metadata
        if metadata is None:
            metadata = {}

        # find the workspace
        workspace = self.__find_workspace(client, ext_name)
        if workspace is None:
            return

        # delete the variable
        try:
            workspace._delete_var(var_name, metadata)
            client.send_short_response()
        except NoSuchVariableException:
            client.send_error('Variable "%s" does not exist in workspace "%s".'
                              % (var_name, ext_name))
        except Exception, exc:
            client.send_error('Internal error: "%s".' % str(exc), 2000)
            raise

    # tuples here encode the properties remove, block, and iterate.
    GET_OP_PROPERTIES = {
    #### name         remove  block   iterate
        'fetch':     (True,   True,   False),
        'fetchTry':  (True,   False,  False),
        'find':      (False,  True,   False),
        'findTry':   (False,  False,  False),
        'ifetch':    (True,   True,   True),
        'ifetchTry': (True,   False,  True),
        'ifind':     (False,  True,   True),
        'ifindTry':  (False,  False,  True),
    }

    ####### Command handler: "fetch", "fetchTry", "find", "findTry"
    ####### Command handler: "ifetch", "ifetchTry", "ifind", "ifindTry"
    def cmd_get(self, client, op_name, ext_name, var_name, var_id='',
                val_index='-999', metadata=None):
        #pylint: disable-msg=R0913
        """NWS Command handler: Get a value from the variable.

          Arguments:
            client          - client connection
            op_name         - operation name (fetch, find, findtry, ifind, etc.)
            ext_name        - the workspace name
            var_name        - the variable name
            var_id          - the variable id (to detect var. re-creation)
            val_index       - the index of the value to read (for iterated operations)
        """
        # Get the operation properties
        props = self.GET_OP_PROPERTIES[op_name]

        # convert null metadata to empty metadata
        if metadata is None:
            metadata = {}

        # Trim whitespace from variable id.  We do this because the variable id
        # is sent in a fixed-width space-padded field.
        var_id = var_id.strip()

        # If this isn't an iterated op, var_id and val_index should be cleared
        if not props[2]:
            var_id = ''
            val_index = -1

        # Convert val_index to an int (always -1 if we have no var_id)
        if var_id:
            val_index = int(val_index)
        else:
            val_index = -1

        # Find the workspace
        workspace = self.__find_workspace(client, ext_name, long_reply=True)
        if workspace is None:
            return

        # Perform the operation
        try:
            iterstate = (var_id, val_index)
            if props[0]:
                response = workspace._fetch_var(var_name, client, props[1],
                                                iterstate, metadata)
            else:
                response = workspace._find_var(var_name, client, props[1],
                                               iterstate, metadata)

            # If the return from the workspace is None, we are blocked, and we
            # are not presently responsible for sending a reply; instead, a
            # reply will be triggered by a later store or by special
            # functionality in a workspace plugin.
            if response is not None:
                client.send_long_response(response)
        except WorkspaceFailure, exc:
            client.send_error(exc.args[0], exc.status, long_reply=True)
        except Exception, exc:
            client.send_error('Internal error: "%s".' % str(exc), 2000,
                              long_reply=True)
            raise

    ####### Command handler: "list vars"
    def cmd_list_vars(self, client, op_name, ext_name, metadata=None):
        """NWS Command handler: List the variables in a workspace.

          Arguments:
            client          - client connection
            op_name         - operation name (not used here)
            ext_name        - the workspace name
        """
        #pylint: disable-msg=W0613

        # convert null metadata to empty metadata
        if metadata is None:
            metadata = {}

        # find the workspace
        workspace = self.__find_workspace(client, ext_name, long_reply=True)
        if workspace is None:
            return

        # list the variables
        try:
            bindings = workspace._get_bindings(hide=True)
            varkeys = bindings.keys()
            varkeys.sort()
            var_listing = '\n'.join([bindings[var_name].format()
                                    for var_name in varkeys])
            client.send_long_response(Response(value=var_listing))
        except Exception, exc:
            client.send_error('Internal error: "%s".' % str(exc), 2000,
                              long_reply=True)
            raise

    ####### Command handler: "list wss"
    def cmd_list_workspaces(self, client, op_name, ext_name_wanted=None,
                            metadata=None):
        #pylint: disable-msg=W0613
        """NWS Command handler: List the workspaces in this server.

          Arguments:
            client          - client connection
            op_name         - operation name (not used here)
            ext_name_wanted - the workspace name, or None to list all workspaces
        """
        # Collect the relevant spaces
        spaces = []
        if not ext_name_wanted:
            all_ext_names = self.__ext_to_int_ws_name.keys()
            all_ext_names.sort()
            for ext_name in all_ext_names:

                # Translate to internal name
                int_name = self.__ext_to_int_ws_name.get(ext_name)
                if int_name is None:
                    continue

                # Get the space
                space = self.spaces.get(int_name)
                if space is None:
                    continue

                spaces.append(space)
        else:
            try:
                int_name = self.__ext_to_int_ws_name[ext_name_wanted]
                space    = self.spaces[int_name]
                spaces.append(space)
            except KeyError:
                pass

        # Format each space
        space_list = []
        for space in spaces:
            int_name     = self.__ext_to_int_ws_name[space.name]
            i_own_this   = client.owned_workspaces.contains(int_name)
            bindings     = space._get_bindings()
            space_list.append('%s%s\t%s\t%s\t%d\t%s' %
                       (' >'[i_own_this],
                        int_name[0],
                        space.owner,
                        space.persistent,
                        len(bindings),
                        var_list_csv(bindings)))

        # Send on the response
        space_list = '\n'.join(space_list) + '\n'
        client.send_long_response(Response(value=space_list))

    ####### Command handler: "mktemp ws"
    def cmd_make_temp_workspace(self, client, op_name, template='__ws__%d',
                                metadata=None):
        #pylint: disable-msg=W0613
        """NWS Command handler: Make a temporary, uniquely named workspace.

          Arguments:
            client          - client connection
            op_name         - operation name (not used here)
            template        - sprintf-style format taking a single integer
                              argument for workspace name
        """
        if metadata is None:
            metadata = {}

        # step the counter on every attempt.
        for _ in range(1000):
            my_count = self.__ws_counter
            self.__ws_counter += 1

            # Build the name
            try:
                new_name = (template % my_count) + self.ws_basename
            except (ValueError, OverflowError, TypeError):
                msg = 'mktemp: bad template "%s".' % template
                log.msg(msg)
                client.send_error(msg, long_reply=True)
                return

            # If we've found a unique name, we're done.
            if not self.__ext_to_int_ws_name.has_key(new_name):
                break
            else:
                new_name = None

        # If we didn't succeed after 100 tries...
        if new_name is None:
            msg = 'mktemp: failed to generate unique name using "%s".' % \
                    template
            log.msg(msg)
            client.send_error(msg, long_reply=True)
            return

        # make a non-owning reference (triggering existence).
        try:
            space = self.__reference_space(new_name,  # ext_name
                                           client,    # client
                                           True,      # can_create
                                           metadata)  # metadata
            assert space is not None
            client.send_long_response(Response(value=new_name))
        except WorkspaceFailure, fail:
            log.msg('Internal error: __reference_space failed unexpectedly.')
            log.msg('                %s' % fail.args[0])
            client.send_error('Internal error: reference_space failed',
                              long_reply=True)

    ####### Command handler: "open ws", "use ws"
    def cmd_open_workspace(self, client, op_name, ext_name, owner_label,
               persistent_str, create_str='yes', metadata=None):
        #pylint: disable-msg=R0913
        """NWS Command handler: Open a workspace.

          Arguments:
            client          - client connection
            op_name         - operation name
            ext_name        - the user-visible workspace name
            owner_label     - extra label for the owner string of a workspace
            persistent_str  - should the workspace be persistent? ('yes'/'no')
            create_str      - should we create the workspace? ('yes'/'no')
        """
        if metadata is None:
            metadata = {}
        create     = create_str == 'yes'
        persistent = persistent_str == 'yes'

        try:
            space = self.__reference_space(ext_name,
                                           client,
                                           create,
                                           metadata)

            # Maybe claim ownership
            if op_name == 'open ws' and space is not None:
                owner = '%s (%s)' % (client.peer, owner_label)
                space._set_owner_info(owner, persistent, metadata)
                client.owned_workspaces.add(space.internal_name)

            # If space is None, we weren't allowed to create ws.
            if space is None:
                client.send_error('No such workspace.', 100)

                # HACK: return failure value to be used by web ui
                return -1
            else:
                client.send_short_response()

                # HACK: return success value to be used by web ui
                return 0

        except WorkspaceFailure, fail:
            client.send_error(fail.args[0], fail.status)

            # HACK: return failure value to be used by web ui
            return -1

    ####### Command handler: "store"
    def cmd_store(self, client, op_name, ext_name, var_name, type_desc, data,
                  metadata=None):
        #pylint: disable-msg=W0613,R0913
        """NWS Command handler: Perform a store operation on a given variable.

          Arguments:
            client          - client connection
            op_name         - operation name (unused)
            ext_name        - workspace name
            var_name        - variable name
            type_desc       - value type descriptor (in string form)
            data            - data to store to the variable
        """
        # convert null metadata to empty metadata
        if metadata is None:
            metadata = {}

        # find the workspace
        workspace = self.__find_workspace(client, ext_name)
        if workspace is None:
            return

        # store the value
        try:
            value = Value(int(type_desc), data)
            workspace._set_var(var_name, client, value, metadata)
            client.send_short_response()
        except WorkspaceFailure, fail:
            client.send_error(fail.args[0], fail.status)
        except Exception, exc:
            client.send_error('Internal error: "%s".' % str(exc), 2000)
            raise

    ####### Command handler: "deadman"
    def cmd_deadman(self, client, op_name, metadata=None):
        #pylint: disable-msg=W0613,R0201
        """NWS Command handler: Deadman operation, signalling the shutdown of
        the server.

          Arguments:
            client          - client connection
            op_name         - operation name
        """
        if metadata is None:
            metadata = {}
        client.mark_for_death()
        client.send_short_response()

    ####### Command dispatch map
    OPERATIONS = {
            'declare var':      cmd_declare_var,
            'delete ws':        cmd_delete_workspace,
            'delete var':       cmd_delete_var,
            'fetch':            cmd_get,
            'fetchTry':         cmd_get,
            'find':             cmd_get,
            'findTry':          cmd_get,
            'ifetch':           cmd_get,
            'ifetchTry':        cmd_get,
            'ifind':            cmd_get,
            'ifindTry':         cmd_get,
            'list vars':        cmd_list_vars,
            'list wss':         cmd_list_workspaces,
            'mktemp ws':        cmd_make_temp_workspace,
            'open ws':          cmd_open_workspace,
            'store':            cmd_store,
            'use ws':           cmd_open_workspace,
            'deadman':          cmd_deadman,
        }

