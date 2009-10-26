#
# Copyright (c) 2005-2008, REvolution Computing, Inc.
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

import os
from twisted.application import internet, service
from twisted.python import log
try:
    from twisted.web import server
except ImportError:
    server = None
    log.msg('WARNING: unable to import twisted.web')
from nwss.server import NwsService, NwsWeb
import nwss

######## Start of configuration section ########
#
# Set interface to 'localhost' to disallow connections from
# other machines.  If you're using an SMP, it might be a good idea.
interface = os.environ.get('NWS_INTERFACE', '')

# Port for the NWS server to listen on
try: nwss.config.nwsServerPort = int(os.environ['NWS_SERVER_PORT'])
except: pass

# Temporary directory for the NWS server
try: nwss.config.nwsTmpDir = os.environ['NWS_TMP_DIR']
except: pass

# Port for the web interface to listen on
try: nwss.config.nwsWebPort = int(os.environ['NWS_WEB_PORT'])
except: pass

# Directory for the web interface to serve files from
try: nwss.config.nwsWebServedDir = os.environ['NWS_WEB_SERVED_DIR']
except: pass

# Size at which we consider a value to be too big for memory
try: nwss.config.nwsLongValueSize = int(os.environ['NWS_LONG_VALUE_SIZE'])
except: pass

# SSL Certificate to use
try: nwss.config.nwsServerSslCert = os.environ['NWS_SERVER_SSL_CERT']
except: pass
try:
    nwss.config.nwsServerSslKey  = os.environ['NWS_SERVER_SSL_KEY']
except:
    if nwss.config.nwsServerSslCert is not None and nwss.config.nwsServerSslCert.count('.') > 0:
        nwss.config.nwsServerSslKey = nwss.config.nwsServerSslCert[0:nwss.config.nwsServerSslCert.rindex('.')] + ".key"

# Plugin directories to use
try:
    nwss.config.nwsPluginDirs = os.environ['NWS_SERVER_PLUGIN_PATH'].split(':')
except:
    nwss.config.nwsPluginDirs = [os.path.join(os.getcwd(), 'plugins')]

#
######## End of configuration section ########

# Create the NWS service
nwssvc = NwsService()
nwssvr = internet.TCPServer(nwss.config.nwsServerPort,
                            nwssvc,
                            interface=interface)

# Create the web interface service if the twisted.web module is installed
if server:
    websvr = internet.TCPServer(nwss.config.nwsWebPort,
                                server.Site(NwsWeb(nwssvc)),
                                interface=interface)
    nwssvc.nwsWebPort = lambda: websvr._port.getHost().port

if not os.environ.get('NWS_NO_SETUID') and hasattr(os, 'getuid') and os.getuid() == 0:
    # we're root, so become user 'daemon'
    application = service.Application('nwss', uid=1, gid=1)
else:
    application = service.Application('nwss')

nwssvr.setServiceParent(application)
if server:
    websvr.setServiceParent(application)
