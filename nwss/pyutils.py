#
# Copyright (c) 2008-2009, REvolution Computing, Inc.
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
"""A few utilities for portability across Python versions."""

__all__ = ['new_list', 'remove_first']

try:
    #pylint: disable-msg=C0103
    from collections import deque   #pylint: disable-msg=W8313
    new_list = deque                #pylint: disable-msg=C0103
    if not hasattr(deque, 'remove'):
        raise ImportError("'deque' class is missing the 'remove' attribute.")
    remove_first = deque.popleft
    clear_list = deque.clear
except ImportError:
    #pylint: disable-msg=C0103
    deque = None
    new_list = list
    remove_first = lambda l: l.pop(0)
    def clear_list(the_list):
        """Replacement for deque.clear when we have to use a list instead of a
        deque."""
        del the_list[:]
