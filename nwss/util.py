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

"""System-level utilities."""

import sys, os
import string       #pylint: disable-msg=W0402

__all__ = ['which', 'msc_quote', 'msc_argv2str']

IS_WINDOWS = sys.platform.startswith('win')
WIN_EXTS = os.environ.get('PATHEXT', '').split(os.pathsep)
NEED_QUOTING = string.whitespace + '"'

def _isexec(path):
    """Check if a path refers to an executable file."""
    return os.path.isfile(path) and os.access(path, os.X_OK)

def _exenames(name):
    """Generate the list of executable names to which ``name`` might refer."""
    names = [name]
    # only expand on Windows
    if IS_WINDOWS:
        # only expand if not extension is specified
        base, ext = os.path.splitext(name)
        if not ext:
            for ext in WIN_EXTS:
                names.append(base + ext)
    return names

def which(cmd, path=None):
    """Find the command ``cmd`` in the path, similar to shell-builtin
    'which'
    """
    if os.path.split(cmd)[0]:
        cmd = os.path.abspath(cmd)
        # print "Checking for", cmd
        matches = [x for x in _exenames(cmd) if _isexec(x)]
    else:
        matches = []
        if not path:
            path = os.environ.get('PATH', os.defpath).split(os.pathsep)
            if IS_WINDOWS:
                path.insert(0, os.curdir)
        for pelem in path:
            full = os.path.join(os.path.normpath(pelem), cmd)
            # print "Checking for", full
            matches += [x for x in _exenames(full) if _isexec(x)]

    return matches

def msc_quote(cmd):
    """Quote a command-line argument as per MSC quoting rules.  This is useful
    in conjunction with os.spawnv on Windows.  For example::

        os.spawnv(os.P_WAIT, argv[0], [msc_quote(a) for a in argv])

    This is only useful on Windows.
    """
    if not [char for char in cmd if char in NEED_QUOTING]:
        return cmd

    quoted = '"'
    nbs = 0

    for char in cmd:
        if char == '\\':
            quoted += char
            nbs += 1
        elif char == '"':
            quoted += (nbs + 1) * '\\' + char
            nbs = 0
        else:
            quoted += char
            nbs = 0

    quoted += nbs * '\\' + '"'
    return quoted

def msc_argv2str(argv):
    """Quote a command-line as per MSC quoting rules.  This is useful in
    conjunction with win32process.CreateProcess and os.system on Windows.  For
    example::

        os.system(msc_argv2str(argv))

    This is only useful on Windows.
    """
    return ' '.join([msc_quote(arg) for arg in argv])

if __name__ == '__main__':
    def _qtest(argv):
        """Simple test for msc_argv2str quoting."""
        print "quoted command string:", msc_argv2str(argv)
    
    def _wtest(argv):
        """Simple test for ``which`` functionality."""
        for arg in argv[1:]:
            plist = which(arg)
            if not plist:
                print >> sys.stderr, \
                        "error: no matches found for", arg
                continue
            if len(plist) > 1:
                print >> sys.stderr, \
                        "warning: more than one match found for", arg
            print plist[0]

    _qtest(sys.argv)
