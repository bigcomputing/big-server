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

"""This module implements the core of the NWS server."""

__version__ = '2.0.0'
__all__ = ['config',
           'server',
           'util',
           'mock',
           'workspace',
           'pyutils',
           'protocol'
           ]

def _cp_int(parser, name, default):
    """Utility to encapsulate loading an integer setting from a config
    file."""
    from ConfigParser import NoOptionError
    try:
        return parser.getint('NWS Server', name)
    except NoOptionError:
        return default

def _cp_str(parser, name, default):
    """Utility to encapsulate loading a string setting from a config
    file."""
    from ConfigParser import NoOptionError
    try:
        return parser.get('NWS Server', name)
    except NoOptionError:
        return default

class Config(object):
    #pylint: disable-msg=R0902,R0903
    """Configuration wrapper object."""

    __slots__ = [ # General server settings
                  'serverport',
                  'tmpdir',
                  'longvaluesize',

                  # web settings
                  'webport',
                  'webserveddir',

                  # SSL settings
                  'serversslcert',
                  'serversslkey',

                  # Plugin settings
                  'plugindirs',

                  # Debug settings
                  'debug'
    ]

    def __init__(self):
        import nwss.config as cfg

        self.serverport    = cfg.nwsServerPort
        self.tmpdir        = cfg.nwsTmpDir
        self.longvaluesize = cfg.nwsLongValueSize

        self.webport       = cfg.nwsWebPort
        self.webserveddir  = cfg.nwsWebServedDir

        self.serversslcert = cfg.nwsServerSslCert
        self.serversslkey  = cfg.nwsServerSslKey

        self.plugindirs    = cfg.nwsPluginDirs

        if hasattr(cfg, 'debug'):
            self.debug     = cfg.debug
        else:
            self.debug     = []

    def is_debug_enabled(self, opt):
        """Check if debugging is enabled for a certain section of the code."""
        optsplit = opt.split(':')
        for scope in range(0, len(optsplit) + 1):
            if scope != 0:
                name_specific = ':'.join(optsplit[0:scope])
                if name_specific in self.debug:
                    return True
            name_all = ':'.join(optsplit[0:scope] + ['ALL'])
            if name_all in self.debug:
                return True
        return False

    def load_from_file(self, filename):
        """Load the configuration from a config file.

          Parameters:
              filename          - name of the config file
        """
        from ConfigParser import ConfigParser
        import os
        parser = ConfigParser()
        parser.read(filename)

        self.serverport    = _cp_int(parser, 'serverPort', self.serverport)
        self.tmpdir        = _cp_str(parser, 'tmpDir', self.tmpdir)
        self.longvaluesize = _cp_int(parser,
                                     'longValueSize',
                                     self.longvaluesize)

        self.webport       = _cp_int(parser, 'webPort', self.webport)
        self.webserveddir  = _cp_str(parser,
                                     'webClientCode',
                                     self.webserveddir)

        self.serversslcert = _cp_str(parser,
                                     'sslCertificate',
                                     self.serversslcert)
        self.serversslkey  = _cp_str(parser, 'sslKey', self.serversslkey)

        plugins = os.pathsep.join(self.plugindirs)
        plugins               = _cp_str(parser, 'pluginsPath', plugins)
        self.plugindirs = plugins.split(os.pathsep)

        debug = ','.join(self.debug)
        debug                 = _cp_str(parser, 'debug', debug)
        self.debug = [opt.strip()
                      for opt in debug.split(',')
                      if opt.strip() != '']

    def __getattr__(self, name):
        name = name.lower()
        if name.startswith('nws'):
            name = name[3:]
        return getattr(self, name)

    def __setattr__(self, name, value):
        name = name.lower()
        if name.startswith('nws'):
            name = name[3:]
        return object.__setattr__(self, name, value)

config = Config()   #pylint: disable-msg=C0103
