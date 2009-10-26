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
#pylint: disable-msg=C0103

"""Configuration settings used throughout the NWS server."""

import tempfile

nwsServerPort = 8765
nwsWebPort = 8766
nwsWebServedDir = 'clientCode'
nwsTmpDir = tempfile.gettempdir()
nwsLongValueSize = 16 * 1024 * 1024
nwsServerSslCert = None
nwsServerSslKey  = None
nwsPluginDirs = ['./plugins']
debug = []
