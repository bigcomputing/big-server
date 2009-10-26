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
Static configuration of Babelfish translators for various scripting languages.
"""

__all__ = ['BABEL_ENGINES', 'MONITOR_ENGINES']

def matlab_translation(deferred, val):
    """Translation callback for Matlab removes trailing newline."""
    deferred.callback(val[:-2]) # strip new lines.

def passthrough_translation(deferred, val):
    """Default callback passes data to the callback verbatim."""
    deferred.callback(val)

BABEL_ENGINES = {1:  ('Python babelfish', passthrough_translation),
                 2:  ('Matlab babelfish', matlab_translation),
                 3:  ('R babelfish',      passthrough_translation),
                 4:  ('Perl babelfish',   passthrough_translation),
                 5:  ('Ruby babelfish',   passthrough_translation),
                 6:  ('Octave babelfish', passthrough_translation),
                 7:  ('Java babelfish',   passthrough_translation),
                 8:  ('CSharp babelfish', passthrough_translation),
                 9:  ('ObjC babelfish',   passthrough_translation),
                 10: ('Elisp babelfish',  passthrough_translation)}

MONITOR_ENGINES = (
    ('Sleigh Monitor', 'Sleigh Monitor',
        ('nodeList', 'totalTasks', 'rankCount', 'workerCount'),
        ('imagefile',)
    ),
    ('Nws Utility', 'Nws Utility',
        ('enableNwsUtility',),
        ('varName', 'value')
    ),
    ('Nws Configurator', 'Nws Configurator',
        ('enableNwsConfigurator',),
        ('varName', 'value')
    ),
    ('chat example', 'Chat Service',
        ('chat',),
        ('msg', 'from')
    ),
)
