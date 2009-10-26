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

'''Templates used in the Web Interface.'''

from urllib import quote_plus

EVEN_ODD = ['even', 'odd']

# modified from twisted's default web file serving.
_STYLE_BLOCK = '''\
<style>
  ul.menu {
    display: block;
    padding: 0 0.3em 0.3em 0.3em;
    background-color: #777;
    margin: 0 0 1em 0;
  }
  ul.menu li {
    display: inline;
    padding: 0 0 0 1em;
  }
  ul.menu a:hover {
    background-color: black;
    text-decoration: none;
  }
  ul.menu a:link, ul.menu a:visited {
    color: white;
    text-decoration: none;
  }
  a:link, a:visited {
    color: blue;
    text-decoration: none;
  }
  .tableheader {
    background-color: #cecece;
  }
  .even {
    background-color: #eee;
  }
  .odd {
    background-color: #dedede;
  }
  .error {
    color: #EE1111;
    font-weight: bold;
    margin: 20;
  }
  .warning {
    color: #EE1111;
    font-weight: bold;
    margin: 20;
  }
  .confirm {
    color: #EE1111;
    font-weight: bold;
    margin: 20;
  }
  .info {
    color: black;
    margin: 20;
  }
  body {
    border: 0;
    padding: 0;
    margin: 0;
    background-color: #efefef;
    font-family: helvetica, sans-serif;
  }
  h1 {
    padding: 0.3em;
    background-color: #777;
    color: white;
    font-size: 1.6em;
    font-style: italic;
    font-weight: bold;
    margin-bottom: 0;
  }
  th {
    text-align: left;
  }
  table form {
    margin-bottom: 0;
  }
  input[value=X] {
    color: #EE1111;
    font-weight: bold;
  }
  .nwstable {
    margin: 0 0 0 1em;
  }
</style>
'''

_HEADER_TEMPLATE = '''<html>
<head>
<title>%(title)s</title>
%(refresh)s
%(style)s
</head>
<body>
<h1>%(title)s</h1>
%(menu)s
'''

_FOOTER_TEMPLATE = '''</body>
</html>
'''

_PAGE_TEMPLATE = '''
%(header)s
%(content)s
%(footer)s
'''

_REFRESH = '''<meta http-equiv="Refresh" content="%d;URL=%s">
'''

CONFIRM_DELETE_VAR_TEMPLATE = '''<p>
<table border="0" cellspacing="0" cellpadding="4">
<tr><td colspan="2" class="confirm">Really delete variable "%(varname)s"?</td></tr>
<tr>
  <td align="center">
    <form action="doit" method="post">
    <input type="hidden" name="op" value="deleteVar">
    <input type="hidden" name="wsName" value="%(wsname)s">
    <input type="hidden" name="varName" value="%(varname)s">
    <input type="submit" value="Yes">
    </form>
  </td>
  <td align="center">
    <form action="doit" method="get">
    <input type="hidden" name="op" value="listVars">
    <input type="hidden" name="wsName" value="%(varname)s">
    <input type="submit" value="No">
    </form>
  </td>
</tr>
</table>'''

CONFIRM_DELETE_WS_TEMPLATE = '''
<table border="0" cellspacing="0" cellpadding="4">
<tr><td colspan="2" class="confirm">Really delete workspace "%(wsname)s"?</td></tr>
<tr>
  <td align="center">
    <form action="doit" method="post">
    <input type="hidden" name="op" value="deleteWs">
    <input type="hidden" name="wsName" value="%(wsname)s">
    <input type="submit" value="Yes">
    </form>
  </td>
  <td align="center">
    <form action="doit" method="get">
    <input type="hidden" name="op" value="listWss">
    <input type="submit" value="No">
    </form>
  </td>
</tr>
</table>'''

CONFIRM_FETCHTRY_VAR_TEMPLATE = '''
<table border="0" cellspacing="0" cellpadding="4">
<tr><td colspan="2" class="confirm">Really fetchTry (i.e. remove) variable "%(varname)s"?</td></tr>
<tr>
  <td align="center">
    <form action="doit" method="post">
    <input type="hidden" name="op" value="fetchTryVar">
    <input type="hidden" name="wsName" value="%(wsname)s">
    <input type="hidden" name="varName" value="%(varname)s">
    <input type="submit" value="Yes">
    </form>
  </td>
  <td align="center">
    <form action="doit" method="get">
    <input type="hidden" name="op" value="showVar">
    <input type="hidden" name="wsName" value="%(wsname)s">
    <input type="hidden" name="varName" value="%(varname)s">
    <input type="submit" value="No">
    </form>
  </td>
</tr>
</table>'''

WS_LIST_TABLE_HEADER = '''
<table cellpadding="4" class="nwstable">
<tr class="tableheader">
  <th>Name</th>
  <th>Monitor</th>
  <th>Owner</th>
  <th>Persistent</th>
  <th># Variables</th>
  <th>Delete?</th>
</tr>
'''

WS_LIST_TABLE_ENTRY_NOMON = '''<tr class="%(class)s">
  <td><a href="doit?op=listVars&wsName=%(wsnameQ)s">%(wsname)s</a></td>
  <td>[none]</td>
  <td>%(owner)s</td>
  <td>%(persistent)s</td>
  <td>%(numbindings)d</td>
  <td>
    <form action="doit" method="post">
    <input type="hidden" name="op" value="confirmDeleteWs">
    <input type="hidden" name="wsName" value="%(wsname)s">
    <input type="submit" value="X">
    </form>
  </td>
</tr>'''

WS_LIST_TABLE_ENTRY_SINGLEMON = '''<tr class="%(class)s">
  <td><a href="doit?op=listVars&wsName=%(wsnameQ)s">%(wsname)s</a></td>
  <td><a href="doit?op=showMonitor&wsName=%(wsnameQ)s&monName=%(monnameQ)s">%(monname)s</a></td>
  <td>%(owner)s</td>
  <td>%(persistent)s</td>
  <td>%(numbindings)d</td>
  <td>
    <form action="doit" method="post">
    <input type="hidden" name="op" value="confirmDeleteWs">
    <input type="hidden" name="wsName" value="%(wsname)s">
    <input type="submit" value="X">
    </form>
  </td>
</tr>'''

WS_LIST_TABLE_ENTRY_MULTIMON = '''<tr class="%(class)s">
  <td><a href="doit?op=listVars&wsName=%(wsnameQ)s">%(wsname)s</a></td>
  <td><a href="doit?op=listMonitors&wsName=%(wsnameQ)s">list monitors</a></td>
  <td>%(owner)s</td>
  <td>%(persistent)s</td>
  <td>%(numbindings)d</td>
  <td>
    <form action="doit" method="post">
    <input type="hidden" name="op" value="confirmDeleteWs">
    <input type="hidden" name="wsName" value="%(wsname)s">
    <input type="submit" value="X">
    </form>
  </td>
</tr>'''

VAR_LIST_HEADER = '''<p>
<table cellpadding="4" class="nwstable">
<tr class="tableheader">
  <th>Variable</th>
  <th># Values</th>
  <th># Fetchers</th>
  <th># Finders</th>
  <th>Mode</th>
  <th>Delete?</th>
</tr>
'''

VAR_LIST_ENTRY = '''<tr class="%(class)s">
  <td><a href="doit?op=showVar&wsName=%(wsnameQ)s&varName=%(varnameQ)s">%(varname)s</a></td>
  <td align="right">%(numvalues)d</td>
  <td align="right">%(numfetchers)d</td>
  <td align="right">%(numfinders)d</td>
  <td>%(mode)s</td>
  <td>
    <form action="doit" method="post">
    <input type="hidden" name="op" value="confirmDeleteVar">
    <input type="hidden" name="wsName" value="%(wsname)s">
    <input type="hidden" name="varName" value="%(varname)s">
    <input type="submit" value="X">
    </form>
  </td>
</tr>
'''

VAR_LIST_FOOTER = '''\
</table>
'''

SERVER_INFO_TEMPLATE = '''<p>
<table cellpadding="4" class="nwstable">
<tr class="tableheader">
  <th>Parameter</th>
  <th>Value</th>
</tr>
<tr class="even">
  <td>Version</td>
  <td>%(nwsversion)s</td>
</tr>
<tr class="odd">
  <td>NWS Server Port</td>
  <td>%(nwsport)d</td>
</tr>
<tr class="even">
  <td>Web Interface Port</td>
  <td>%(webport)d</td>
</tr>
<tr class="odd">
  <td>Temp Directory</td>
  <td>%(tmpdir)s</td>
</tr>
<tr class="even">
  <td>Long Value Size</td>
  <td>%(longvaluesize)d</td>
</tr>
</table>
'''

CLIENT_LIST_HEADER = '''<p>
<table cellpadding="4" class="nwstable">
<tr class="tableheader">
  <th>Client</th>
  <th>Session #</th>
  <th># Ops</th>
  <th># Long Values</th>
  <th># Wss Owned</th>
  <th>Last Op</th>
  <th>Blocking</th>
  <th>Ws and var</th>
  <th>Time of Last Op</th>
</tr>
'''

CLIENT_LIST_ENTRY = '''\
<tr class="%(class)s">
  <td>%(peer)s</td>
  <td>%(sessionno)d</td>
  <td>%(numops)d</td>
  <td>%(numlong)d</td>
  <td>%(numws)d</td>
  <td>%(lastop)s</td>
  <td>%(blocking)s</td>
  <td>%(blockingvar)s</td>
  <td>%(lasttime)s</td>
</tr>
'''

CLIENT_LIST_FOOTER = '''\
</table>
'''

def make_div(content, cls):
    """Utility to assemble a DIV html element.

      Parameters:
          content           - html for inside the DIV
          cls               - CSS class for the DIV
    """
    return '<div class="%s">%s</div>' % (cls, content)

def menu_provider_default(nwslabel='NetWorkSpaces',
                          clientslabel='Clients'):
    """Utility to assemble the default menu.

      Parameters:
          nwslabel          - label override for ``listWss`` page
    """
    yield 'doit?op=showServerInfo', 'Server Info'
    yield 'doit?op=listClients',    clientslabel,
    yield 'doit?op=listWss',        nwslabel,

def menu_provider_ws(wsname, varslabel='Variables'):
    """Utility to assemble the menu for workspace-specific pages.

      Parameters:
          wsname            - name of the current workspace
          nwslabel          - label override for ``listVars`` page
    """
    for item in menu_provider_default():
        yield item

    wsname = quote_plus(wsname)
    yield ('doit?op=listVars&wsName=%s' % wsname), varslabel

def menu_provider_var(wsname, varname):
    """Utility to assemble the menu for variable-specific pages.

      Parameters:
          wsname            - name of the current workspace
          varname           - name of the current variable
    """
    for item in menu_provider_ws(wsname):
        yield item

    wsname  = quote_plus(wsname)
    varname = quote_plus(varname)
    url = ('doit?op=showVar&wsName=%s&varName=%s' % (wsname, varname))
    yield url, 'Values'

def menu_provider_refresh(url, base):
    """Utility to add a 'Refresh' item to the menu bar.

      Parameters:
          url               - URL for the 'Refresh' item
          base              - base menu provider
    """
    for item in base:
        yield item

    yield url, 'Refresh'

def make_menu(provider):
    """Generate an appropriate 'menu' for a page.

      Parameters:
          provider          - iterable yielding URL/label pairs for menu
    """
    prefix  = '<ul class="menu">\n'
    content = ['  <li><a href="%s">%s</a></li>' % x for x in provider]
    suffix  = '\n</ul>\n'
    return prefix + '\n'.join(content) + suffix

def _make_refresh(page, delay=3):
    """Generate an appropriate <meta refresh=''> tag.  If page is None, the
    empty string will be returned.

      Parameters:
          page              - page to redirect to
          delay             - delay in seconds (default: 3)
    """
    if page is None:
        return ''
    return _REFRESH % (delay, page)

def make_header(title, menu=None, refresh_url=None):
    """Build a page header from the given parameters.

      Parameters:
          title             - title for page
          menu              - content for menu
          refresh_url       - META refresh URL, if any
    """
    if menu is None:
        menu = menu_provider_default()
    fields = {
            'title':   title,
            'style':   _STYLE_BLOCK,
            'menu':    make_menu(menu),
            'refresh': _make_refresh(refresh_url),
    }
    return _HEADER_TEMPLATE % fields

def make_footer(title):
    """Build a page footer from the given parameters.

      Parameters:
          title             - title for page
    """
    fields = {
            'title':   title,
    }
    return _FOOTER_TEMPLATE % fields

def make_page(title, content, refresh_url=None, menu=None):
    """Build a complete page from the given parameters.

      Parameters:
          title             - title for page
          content           - content for page (HTML)
          refresh_url       - META refresh URL, if any
          menu              - content for menu
    """
    fields = {
            'header':  make_header(title, menu, refresh_url),
            'footer':  make_footer(title),
            'title':   title,
            'content': content,
    }
    return _PAGE_TEMPLATE % fields

def make_errpage(msg, title='Error', **kwargs):
    """Create a stock error page with a given message and title.

      Parameters:
          msg               - error message (HTML)
          title             - title (HTML)
          kwargs            - other arguments, as per ``make_page``
    """
    error_div = make_div(msg, 'error')
    return make_page(title, error_div, **kwargs)

def make_infopage(msg, title='Info', **kwargs):
    """Create a stock info page with a given message and title.

      Parameters:
          msg               - message (HTML)
          title             - title (HTML)
          kwargs            - other arguments, as per ``make_page``
    """
    info_div = make_div(msg, 'info')
    return make_page(title, info_div, **kwargs)

