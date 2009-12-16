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

# TODO: uniformly cope with get encodings
# TODO: rework Translator/Monitor

"""NWS Web UI implementation."""

import traceback
import os
from cgi import escape
from urllib import quote_plus

from twisted.web import resource, server as webserver, static
from twisted.internet import defer
from twisted.python import log

from nwss.mock import DummyConnection
from nwss.engines import MONITOR_ENGINES
from nwss.engines import BABEL_ENGINES

import nwss
from nwss.base import Value, DIRECT_STRING
from nwss.webtemplates import *         #pylint: disable-msg=W0401

PYTHON_ENVIRONMENT =     0x01000000
_DEBUG = nwss.config.is_debug_enabled('NWS:web')

def translate_value(server, value, callback, *extra_args):
    """Translate a value by sending it to the appropriate babelfish, sending on
    the translated value to the supplied callback.

      Arguments:
        server     - server whose babelfish to attach to
        value      - value to translate
        callback   - callback to receive babelfish-translated value
        extra_args - arguments for callback
    """
    if not isinstance(value, Value):
        callback(str(value), *extra_args)
        return
    if value.is_large():
        callback('<long value>', *extra_args)
        return
    elif value.type_descriptor & DIRECT_STRING:
        callback(value.val(), *extra_args)
        return

    deferred = defer.Deferred()
    deferred.addCallback(callback, *extra_args)
    environment_id = (value.type_descriptor >> 24) & 0xFF

    try:
        babelfish_ws_name, val_callback = BABEL_ENGINES[environment_id]

        def send_reply(status, metadata, value):
            #pylint: disable-msg=W0613
            """Callback for data from the babelfish."""
            log.msg('Value.val(): %s' % repr(value.val()))
            val_callback(deferred, value.val())
        client = DummyConnection(send_reply)

        status = use_workspace(server, client, babelfish_ws_name, False)
        if status == 0:
            server.cmd_store(client, 'store', babelfish_ws_name, 'food',
                             value.type_descriptor, value.val())
            server.cmd_get(client, 'fetch', babelfish_ws_name, 'doof')
        else:
            deferred.callback('[error: %s not running]' % babelfish_ws_name)
    except KeyError:
        deferred.callback('[error: unknown babel engine]')


def get_binding(space, var_name):
    """Get the variable binding ``var_name`` for the workspace ``space``, or
    None if there is no such binding.

      Parameters:
          space             - the workspace object
          var_name          - the variable binding to get
    """
    #pylint: disable-msg=W0212
    return space._get_binding(var_name, True)

def get_bindings(space):
    """Get all variable bindings for the workspace ``space``.

      Parameters:
          space             - the workspace object
    """
    #pylint: disable-msg=W0212
    return space._get_bindings(True)

def use_workspace(server, conn, ws_name, create=True):
    """Open the workspace ``ws_name`` for the given connection to the NWS
    server.

      Parameters:
          server            - the NWS server
          conn              - the connection to the server
          ws_name           - the workspace name
    """
    if create:
        return server.cmd_open_workspace(conn, 'use ws', ws_name, '',
                                         'no')
    else:
        return server.cmd_open_workspace(conn, 'use ws', ws_name, '',
                                         'no', 'no')


def has_all_keys(dictionary, klist):
    """Check if ``dictionary`` has every key in the iterable ``klist``.

      Parameters:
          dictionary        - the dictionary to check
          klist             - the iterable containing the keys
    """
    for key in klist:
        if not dictionary.has_key(key):
            return False
    return True

# here are a number of functions that generate html for error messages
def errpage_no_workspace(ws_name):
    """Build an HTML error page indicating that the workspace ``ws_name`` was
    not found.

      Parameters:
          ws_name           - missing workspace name.
    """
    message = 'There is currently no workspace named %s.' % escape(ws_name)
    return make_errpage(message)

def errpage_monitor_not_running(mon_name):
    """Build an HTML error page indicating that the monitor ``mon_name`` was
    not running.

      Parameters:
          mon_name          - missing monitor name.
    """
    message = '%s not running.' % escape(mon_name)
    return make_errpage(message)

def errpage_invalid_ws_for_monitor(ws_name):
    """Build an HTML error page indicating that the workspace ``ws_name`` was
    invalid for the requested monitor.

      Parameters:
          ws_name           - invalid workspace
    """
    message = 'Invalid workspace specified for monitor: %s' % escape(ws_name)
    return make_errpage(message)

def errpage_variable_not_found(var_name, ws_name):
    """Build an HTML error page indicating that the variable ``var_name`` was
    not found in the workspace ``ws_name``.

      Parameters:
          ws_name           - the workspace
          var_name          - the variable
    """
    message = 'No variable named %s currently in "%s"' % \
         (escape(var_name), escape(ws_name))
    return make_errpage(message, wsname=ws_name)

def errpage_no_monitor(mon_name):
    """Build an HTML error page indicating that the monitor ``mon_name`` was
    not found.

      Parameters:
          mon_name          - missing monitor name.
    """
    message = 'No monitor found for %s' % escape(mon_name)
    return make_errpage(message)

def errpage_malformed_request():
    """Build an HTML error page indicating that the last request was somehow
    malformed.
    """
    return make_errpage('Malformed request.')

def errpage_monitor_error(msg):
    """Build an HTML error page indicating some error has occurred inside the
    monitor for a workspace.

      Parameters:
          msg               - description of the error
    """
    message = 'Error monitoring workspace: %s' % msg
    return make_errpage(message)

def errpage_static_server_error(dirname):
    """Build an HTML error page indicating a problem with the static content
    directory ``dirname``.

      Parameters:
          dirname           - the static content dir which was invalid
    """
    message = 'Cannot serve files from directory "%s".' % dirname
    return make_errpage(message)

def infopage_ws_deleted(ws_name):
    """Build an HTML info page indicating that the workspace ``ws_name`` has
    been successfully deleted.

      Parameters:
          ws_name           - the workspace which was deleted
    """
    message = 'NetWorkSpace "%s" was deleted.' % escape(ws_name)
    return make_infopage(message, 
                    'Workspace Deleted',
                    refresh_url='doit?op=listWss')

def infopage_var_deleted(ws_name, var_name):
    """Build an HTML info page indicating that the variable ``var_name`` has
    been successfully deleted from the workspace ``ws_name``.

      Parameters:
          ws_name           - the workspace name
          var_name          - the variable which was deleted
    """
    message = 'Variable "%s" in "%s" was deleted.' % \
            (escape(var_name), escape(ws_name))
    refresh_url = 'doit?op=listVars&wsName=%s&varName=%s' % \
            (quote_plus(ws_name), quote_plus(var_name))
    return make_infopage(message,
                    'Variable Deleted',
                    refresh_url=refresh_url)

def infopage_var_fetched(ws_name, var_name):
    """Build an HTML info page indicating that the variable ``var_name`` has
    been successfully fetched (i.e. its first value removed) from the workspace
    ``ws_name``.

      Parameters:
          ws_name           - the workspace name
          var_name          - the variable which was fetched
    """
    message = 'Value in variable "%s" was (possibly) removed.' % \
              escape(var_name)
    refresh_url = 'doit?op=showVar&wsName=%s&varName=%s' % \
            (quote_plus(ws_name), quote_plus(var_name))
    return make_infopage(message,
                    'Variable Deleted',
                    refresh_url=refresh_url,
                    wsname=ws_name,
                    varname=var_name)
                 
class Translator:
    #pylint: disable-msg=R0903
    """Utility class to encapsulate communication with the Babelfish."""

    def __init__(self, request, ws_name, var_name, num_values):
        self.request  = request
        self.ws_name  = ws_name
        self.var_name = var_name
        self.num_values = num_values
        self.pop = 0
        self.queue = [None] * self.num_values
        self.title = 'Values in %s' % escape(self.var_name)

    def run(self, server, var_vals, truncated):
        """Send the variable values to the Babelfish and stream the response to
        the HTTP client.
        """
        url = 'doit?op=showVar&wsName=%s&varName=%s' % \
                (quote_plus(self.ws_name), self.var_name)
        menubase = menu_provider_var(self.ws_name, self.var_name)
        menu = menu_provider_refresh(url, menubase)
        self.request.write(make_header(self.title, menu))

        if truncated:
            msg = 'Display has been truncated to %d values.' % self.num_values
            self.request.write(make_div('warning', msg))
        self.request.write('<ol>\n')

        # we kick off all translations here, rather than ping/pong-ing
        # them. we do this to avoid problems with the list of values
        # changing as the process unfolds.
        if 0 == self.num_values:
            self.__close_page()
        else:
            for idx, val in zip(xrange(self.num_values), var_vals):
                translate_value(server, val, self.__callback, idx)

    def __callback(self, text, idx):
        """Collect translated values from the Babelfish.

          Parameters:
              text          - translated text
              idx           - index of translated item
        """
        self.queue[idx] = escape(text)
        self.pop += 1
        if self.pop == self.num_values:
            oddness = 0
            for item in self.queue:
                if item is None:
                    log.msg('Unescaped text: %s' % repr(text))
                    self.request.write('<li class="%s"></li>\n' %
                                       (EVEN_ODD[oddness]))
                else:
                    self.request.write('<li class="%s">%s</li>\n' %
                                       (EVEN_ODD[oddness],
                                           item.replace('\n', '<br>')))
                oddness = 1 - oddness
            self.__close_page()

    def __close_page(self):
        """Write the page footer, closing the enclosed HTML tags."""
        self.request.write('</ol>\n')
        self.request.write(make_footer(self.title))
        self.request.finish()

class Monitor:
    #pylint: disable-msg=R0903
    """Communicates with one of the monitors."""

    def __init__(self, server, request, mon_name, reply_var_name):
        self.server = server
        self.request = request
        self.mon_name = mon_name
        self.arg_count = -1
        self.error = 0
        self.reply_var_name = reply_var_name
        self.dummy_conn = DummyConnection(self.__send_reply, peer_id='Monitor')

    def run(self, ws_name):
        """Run this monitor attached to the workspace ``ws_name``, pushing the
        result out to the HTTP client.
        """
        mon_name = self.mon_name
        request = self.request
        eng = [me for me in MONITOR_ENGINES if me[0] == mon_name]
        if not eng:
            log.msg('error: no monitor found for ' + mon_name)
            self.request.write(errpage_no_monitor(mon_name))
            self.request.finish()
            return

        # 'args' is a tuple of the request arguments that the monitor
        # is interested in
        args = eng[0][3]

        use_workspace(self.server, self.dummy_conn, mon_name)

        if _DEBUG:
            log.msg('Monitor: storing request')
        # note that this doesn't currently support multiple values for arguments
        monargs = {}
        numargs = 0
        for arg in args:
            if request.args.has_key(arg):
                monargs[arg] = request.args[arg]
                numargs += len(monargs[arg])

        monargs['wsName'] = [ws_name]
        monargs['replyVarName'] = [self.reply_var_name]
        numargs += 2

        # note: this code assumes only one monitor process per workspace.
        # store the number of arguments, followed by the arguments
        # in NAME=VALUE form
        desc = PYTHON_ENVIRONMENT | DIRECT_STRING
        self.server.cmd_store(self.dummy_conn, 'store', mon_name, 'request',
                desc, str(numargs))
        for key, val_list in monargs.items():
            assert type(val_list) == list
            for val in val_list:
                assert type(val) == str
                self.server.cmd_store(self.dummy_conn,
                                      'store',
                                      mon_name,
                                      'request',
                                      desc,
                                      key + '=' + val)

        if _DEBUG:
            log.msg('Monitor: fetching reply')
        self.server.cmd_get(self.dummy_conn,
                            'fetch',
                            mon_name,
                            self.reply_var_name)
        if _DEBUG:
            log.msg('Monitor: get returned')

    def __handle_header_count(self, data):
        """Handle the header count.  The header count is the first item sent
        back from the monitor, and gives the number of HTTP headers which the
        monitor is going to send.

          Parameters:
              data              - the text of the header count field
        """
        arg_count = -1
        if self.error:
            log.msg('Monitor: ignoring header count due to previous ' + \
                    'error (argCount < 0)')
        else:
            try:
                arg_count = int(data)
            except ValueError:
                log.msg('Monitor: got bad value for header count: %s' % \
                             data)
                self.error = 1
                self.request.setHeader('content-type', 'text/html')
                response = 'got bad value for header count'
                self.request.write(errpage_monitor_error(response))
                self.request.finish()
            else:
                if _DEBUG:
                    log.msg('Monitor: %d headers coming' % arg_count)
                self.server.cmd_get(self.dummy_conn,
                                    'fetch',
                                    self.mon_name,
                                    self.reply_var_name)
        return arg_count

    def __handle_header_value(self, data):
        """Handle a header value.  A header value is an item of the form
        key=value sent back from the monitor, which is turned into an HTTP
        header sent back to the client.

          Parameters:
              data              - the text of the header field
        """
        if self.error:
            log.msg('Monitor: ignoring header due to previous ' + \
                    'error (argCount = %d)' % (self.arg_count + 1,))
            self.server.cmd_get(self.dummy_conn,
                                'fetch',
                                self.mon_name,
                                self.reply_var_name)
        else:
            try:
                key, val = [x.strip() for x in data.split('=', 1)]
            except ValueError:
                log.msg('Monitor: error handling header specification: %s' % \
                             data)
                self.error = 1
                self.request.setHeader('content-type', 'text/html')
                response = errpage_monitor_error(
                        'error handling header specification')
                self.request.write(response)
                self.request.finish()
            else:
                if _DEBUG:
                    log.msg('Monitor: got a header; %s = %s' % \
                            (repr(key), repr(val)))
                self.request.setHeader(key, val)
                if _DEBUG:
                    log.msg('Monitor: got a header; %d more coming' % \
                            self.arg_count)
                self.server.cmd_get(self.dummy_conn,
                                    'fetch',
                                    self.mon_name,
                                    self.reply_var_name)

    def __handle_payload(self, status, data):
        """Handle the payload.  The payload is raw data to send back to the
        HTTP client from the monitor.

          Parameters:
              data              - the text of the payload
        """
        if _DEBUG:
            log.msg('Monitor: got the payload')
        if self.error:
            log.msg('Monitor: ignoring payload value due to previous ' + \
                    'error (argCount is 0)')
        else:
            if status:
                # XXX: this is incorrect if the browser expects an image...
                log.msg('Monitor: bad status = ' + str(status))
                self.request.setHeader('content-type', 'text/html')
                page = errpage_monitor_error('status = %d' % status)
                self.request.write(page)
            else:
                self.request.write(data)

            self.request.finish()

            # it will be an error if __send_reply is called again
            self.error = 1

            self.server.delete_var(self.dummy_conn,
                                   'delete var',
                                   self.mon_name,
                                   self.reply_var_name)
            if _DEBUG:
                log.msg('Monitor: finished browser reply')

    def __send_reply(self, status, metadata, value):
        #pylint: disable-msg=W0613, R0913
        """Callback for the dummy connection to receive replies from the
        monitor.
        """
        if value is None:
            return
        if _DEBUG:
            log.msg('Monitor: monitor replied')

        if self.arg_count < 0:
            self.arg_count = self.__handle_header_count(value.val())
        elif self.arg_count > 0:
            self.__handle_header_value(value.val())
            self.arg_count -= 1
        else:
            self.__handle_payload(status, value.val())

class NwsWebDynamic(resource.Resource):
    """Twisted Web handler for dynamic content.  Displays a view of the
    internal state of the NWS server.
    """

    isLeaf = True # never call getChild, go to render_GET directly.

    def __init__(self, nws_server):
        resource.Resource.__init__(self)

        self.int_names = nws_server.get_ext_to_int_mapping()
        self.spaces = nws_server.spaces
        self.dummy_conn = DummyConnection(peer_id='NwsWebDynamic')
        self.nws_server = nws_server
        self.monid = 0

    def __get_space(self, ext_name):
        """Get the workspace whose external name is ``ext_name``.  Returns None
        if the workspace cannot be found.

          Parameters:
              ext_name          - the workspace external name
        """
        int_name = self.int_names.get(ext_name)
        if int_name is None:
            return None
        return self.spaces.get(int_name)

    def __confirm_delete_var(self, request):
        #pylint: disable-msg=R0201
        """Handler for the ``confirmDeleteVar`` page."""
        var_name = request.args['varName'][0]
        ws_name = request.args['wsName'][0]
        fields = {
                'wsname':  escape(ws_name),
                'varname': escape(var_name),
        }
        content = CONFIRM_DELETE_VAR_TEMPLATE % fields
        return make_page('Confirm Variable Deletion',
                         content)

    def __confirm_delete_ws(self, request):
        #pylint: disable-msg=R0201
        """Handler for the ``confirmDeleteWs`` page."""
        ws_name = request.args['wsName'][0]
        fields = {
                'wsname':  escape(ws_name),
        }
        content = CONFIRM_DELETE_WS_TEMPLATE % fields
        return make_page('Confirm Workspace Deletion', content)

    def __confirm_fetchtry_var(self, request):
        #pylint: disable-msg=R0201
        """Handler for the ``confirmFetchTryVar`` page."""
        ws_name  = request.args['wsName'][0]
        var_name = request.args['varName'][0]
        fields = {
                'wsname':  escape(ws_name),
                'varname': escape(var_name),
        }
        content = CONFIRM_FETCHTRY_VAR_TEMPLATE % fields
        return make_page('Confirm FetchTry',
                         content,
                         menu=make_menu(menu_provider_var(ws_name, var_name)))

    def __delete_var(self, request):
        """Handler for the ``deleteVar`` page."""
        ws_name = request.args['wsName'][0]
        var_name = request.args['varName'][0]

        # Get space
        space = self.__get_space(ws_name)
        if space is None:
            return errpage_no_workspace(ws_name)

        # Get binding
        value = get_binding(space, var_name)
        if value is None:
            return errpage_variable_not_found(var_name, ws_name)

        use_workspace(self.nws_server, self.dummy_conn, ws_name)
        self.nws_server.cmd_delete_var(self.dummy_conn,
                                   'delete var',
                                   ws_name,
                                   var_name)
        return infopage_var_deleted(ws_name, var_name)

    def __delete_ws(self, request):
        """Handler for the ``deleteWs`` page."""
        ws_name = request.args['wsName'][0]

        # Get space
        space = self.__get_space(ws_name)
        if space is None:
            return errpage_no_workspace(ws_name)

        self.nws_server.cmd_delete_workspace(self.dummy_conn,
                                             'delete ws',
                                             ws_name)
        return infopage_ws_deleted(ws_name)

    def __list_wss(self, request):
        #pylint: disable-msg=W0613
        """Handler for the ``listWss`` page."""
        ext_names = self.int_names.keys()
        ext_names.sort()
        version = escape(nwss.__version__)
        title = 'NetWorkSpaces %s' % version
        ws_list_html = make_header(title, menu_provider_default('Refresh'))
        ws_list_html += WS_LIST_TABLE_HEADER

        oddness = 0
        for ext_name in ext_names:
            space = self.__get_space(ext_name)
            bindings = get_bindings(space)
            monitors = [mentry for mentry in MONITOR_ENGINES
                        if has_all_keys(bindings, mentry[2])]

            fields = {
                    'class':       EVEN_ODD[oddness],
                    'wsname':      escape(ext_name),
                    'wsnameQ':     quote_plus(ext_name),
                    'owner':       escape(space.owner),
                    'persistent':  str(space.persistent),
                    'numbindings': len(bindings),
            }
            if len(monitors) > 1:
                ws_list_html += WS_LIST_TABLE_ENTRY_MULTIMON % fields
            elif len(monitors) == 1:
                mon_name = monitors[0][0]
                display_name = monitors[0][1]
                fields['monnameQ'] = quote_plus(mon_name)
                fields['monname']  = escape(display_name)
                ws_list_html += WS_LIST_TABLE_ENTRY_SINGLEMON % fields
            else:
                ws_list_html += WS_LIST_TABLE_ENTRY_NOMON % fields

            oddness = 1 - oddness

        ws_list_html += '</table>\n'
        ws_list_html += make_footer(title)
        return ws_list_html

    def __show_monitor(self, request):
        """Handler for the ``showMonitor`` page."""
        ws_name = request.args['wsName'][0]
        mon_name = request.args['monName'][0]

        # Get space
        space = self.__get_space(ws_name)
        if space is None:
            return errpage_no_workspace(ws_name)
        vbindings = get_bindings(space)

        # Get monitor space
        mon_space = self.__get_space(mon_name)
        if mon_space is None:
            return errpage_monitor_not_running(mon_name)

        # verify that the ws_name workspace qualifies to be handled by mon_name
        monlist = [mentry[0] for mentry in MONITOR_ENGINES
                   if has_all_keys(vbindings, mentry[2])]
        if mon_name not in monlist:
            return errpage_invalid_ws_for_monitor(ws_name)

        reply_name = 'reply_%d' % self.monid
        mon = Monitor(self.nws_server, request, mon_name, reply_name)
        mon.run(ws_name)
        self.monid += 1
        if self.monid > 1000000:
            self.monid = 0
        return webserver.NOT_DONE_YET

    def __list_monitors(self, request):
        """Handler for ``listMonitors`` page."""
        ws_name = request.args['wsName'][0]

        # Get space
        space = self.__get_space(ws_name)
        if space is None:
            return errpage_no_workspace(ws_name)
        vbindings = get_bindings(space)

        # Build content
        content = '<p>\n<ul>\n'
        for monitor in MONITOR_ENGINES:
            if not has_all_keys(vbindings, monitor[2]):
                continue

            content += '''\
<li><a href="doit?op=showMonitor&wsName=%s&monName=%s">%s</a></li>
''' % (quote_plus(ws_name), quote_plus(monitor[0]), escape(monitor[1]))
        content += '</ul>\n'

        return make_page('Monitors for %s' % escape(ws_name),
                         content)

    def __list_vars(self, request):
        """Handler for ``listVars`` page."""
        ws_name = request.args['wsName'][0]

        # Get space
        space = self.__get_space(ws_name)
        if space is None:
            return errpage_no_workspace(ws_name)
        vbindings = get_bindings(space)

        var_names = vbindings.keys()
        var_names.sort()

        content = VAR_LIST_HEADER

        fields = {
                'wsname':       escape(ws_name),
                'wsnameQ':      quote_plus(ws_name),
        }
        oddness = 0
        for var_name in var_names:
            var      = vbindings[var_name]
            fields['class']       = EVEN_ODD[oddness]
            fields['varname']     = escape(var_name)
            fields['varnameQ']    = quote_plus(var_name)
            fields['mode']        = var.mode()
            fields['numvalues']   = var.num_values
            fields['numfetchers'] = var.num_fetchers
            fields['numfinders']  = var.num_finders
            content += VAR_LIST_ENTRY % fields
            oddness = 1 - oddness

        content += VAR_LIST_FOOTER
        return make_page('Variables in %s' % escape(ws_name),
                         content,
                         menu=menu_provider_ws(ws_name, 'Refresh'))

    def __show_var(self, request):
        """Handler for ``showVar`` page."""
        ws_name  = request.args['wsName'][0]
        var_name = request.args['varName'][0]

        # Get space
        space = self.__get_space(ws_name)
        if space is None:
            return errpage_no_workspace(ws_name)
        vbinding = get_binding(space, var_name)
        if vbinding is None:
            return errpage_variable_not_found(var_name, ws_name)

        var_vals = vbinding.values()

        # truncate the number of values to something reasonable
        num_values = vbinding.num_values
        if num_values > 1000:
            num_values = 1000
            truncated = True
        else:
            truncated = False

        xlat = Translator(request, ws_name, var_name, num_values)
        xlat.run(self.nws_server, var_vals, truncated)
        return webserver.NOT_DONE_YET

    def __fetchtry_var(self, request):
        """Handler for ``fetchTryVar`` page."""
        ws_name  = request.args['wsName'][0]
        var_name = request.args['varName'][0]
        use_workspace(self.nws_server, self.dummy_conn, ws_name)
        self.nws_server.cmd_get(self.dummy_conn, 'fetchTry', ws_name, var_name)
        return infopage_var_fetched(ws_name, var_name)

    def __show_server_info(self, request):
        #pylint: disable-msg=W0613,R0201
        """Handler for ``showServerInfo`` page."""
        fields = {
                'nwsversion':       escape(nwss.__version__),
                'nwsport':          nwss.config.nwsServerPort,
                'webport':          nwss.config.nwsWebPort,
                'tmpdir':           escape(nwss.config.nwsTmpDir),
                'longvaluesize':    nwss.config.nwsLongValueSize,
        }
        return make_page('Server Info', SERVER_INFO_TEMPLATE % fields)

    def __list_clients(self, request):
        #pylint: disable-msg=W0613
        """Handler for ``listClients`` page."""
        content = CLIENT_LIST_HEADER

        oddness = 0
        for client in self.nws_server.protocols.values():
            last_op, last_time = client.last_operation
            if client.blocking_var is not None:
                blocking_var = escape(client.blocking_var)
            else:
                blocking_var = ''
            fields = {
                    'class':            EVEN_ODD[oddness],
                    'peer':             escape(client.peer),
                    'sessionno':        client.transport.sessionno,
                    'numops':           client.num_operations,
                    'numlong':          client.num_long_values,
                    'numws':            client.owned_workspaces.count,
                    'lastop':           escape(last_op),
                    'blocking':         str(client.blocking),
                    'blockingvar':      blocking_var,
                    'lasttime':         escape(last_time)
            }
            content += CLIENT_LIST_ENTRY % fields
            oddness = 1 - oddness

        content += CLIENT_LIST_FOOTER

        return make_page('Clients',
                         content,
                         menu=menu_provider_default(clientslabel='Refresh'))

    OP_TABLE = {
        'confirmDeleteVar':         __confirm_delete_var,
        'confirmDeleteWs':          __confirm_delete_ws,
        'deleteVar':                __delete_var,
        'deleteWs':                 __delete_ws,
        'confirmFetchTryVar':       __confirm_fetchtry_var,
        'fetchTryVar':              __fetchtry_var,
        'listVars':                 __list_vars,
        'listWss':                  __list_wss,
        'showVar':                  __show_var,
        'showMonitor':              __show_monitor,
        'listMonitors':             __list_monitors,
        'listClients':              __list_clients,
        'showServerInfo':           __show_server_info,
    }

    def render_GET(self, request):
        #pylint: disable-msg=C0103
        """Callback from Twisted Web to field GET requests."""
        try:
            request.setHeader('cache-control', 'no-cache')
            op_name = request.args.get('op', ['listWss'])[0]
            return self.OP_TABLE.get(op_name, self.__list_wss)(self, request)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception, exc:  #pylint: disable-msg=W0703
            traceback.print_exc()
            log.err(exc)
            return errpage_malformed_request()

    def render_POST(self, request):
        #pylint: disable-msg=C0103
        """Callback from Twisted Web to field POST requests."""
        try:
            request.setHeader('cache-control', 'no-cache')
            op_name = request.args.get('op', ['listWss'])[0]
            return self.OP_TABLE.get(op_name, self.__list_wss)(self, request)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception, exc:  #pylint: disable-msg=W0703
            traceback.print_exc()
            log.err(exc)
            return errpage_malformed_request()

class NwsWeb(resource.Resource):
    """Root web server for NWS web service.  Contains a static directory and a
    dynamic directory, the latter of which allows browsing the internal state
    of the NWS server.
    """

    def __init__(self, nws_server):
        resource.Resource.__init__(self)

        self.dynamic = NwsWebDynamic(nws_server)

        log.msg('clientCode served from directory ' +
                   nwss.config.nwsWebServedDir)

        if os.path.isdir(nwss.config.nwsWebServedDir):
            client_code = static.File(nwss.config.nwsWebServedDir)
            client_code.contentTypes.update({
                '.m': 'text/plain', '.M': 'text/plain',
                '.py': 'text/plain', '.PY': 'text/plain',
                '.r': 'text/plain', '.R': 'text/plain'})
        else:
            log.msg("clientCode directory doesn't exist")
            page = errpage_static_server_error(nwss.config.nwsWebServedDir)
            client_code = static.Data(page, 'text/html')
        self.putChild('clientCode', client_code)

    def getChild(self, name, request):
        #pylint: disable-msg=W0613,C0103
        """Callback from Twisted to get the handler for a specific URL.  In
        this case, unless it matched the 'static content' directory, we want to
        forward it to the dynamic content provider.
        """
        return self.dynamic
