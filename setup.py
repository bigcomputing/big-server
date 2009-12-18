#!/usr/bin/env python
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

"""
Distutils installer for NetWorkSpaces
"""
import os, sys

if sys.version_info < (2, 2):
    print >> sys.stderr, "You must use at least Python 2.2 for NetWorkSpaces"
    sys.exit(1)

if os.environ.get('NWS_TAC_DIR'):
    tacdir = os.environ['NWS_TAC_DIR']
elif hasattr(os, 'getuid') and os.getuid() == 0:
    tacdir = '/etc'
else:
    tacdir = ''

if os.environ.get('NWS_DOC_DIR'):
    docdir = os.environ['NWS_DOC_DIR']
elif hasattr(os, 'getuid') and os.getuid() == 0:
    docdir = '/usr/share/doc/nws-server'
else:
    docdir = 'nws-server'

top_srcdir = os.environ.get('NWS_TOP_SRCDIR', '.')
doc_files = [os.path.join(top_srcdir, x) for x in ['README']]

scripts = []
if os.environ.get('NWS_WINDOWS', 'no') == 'yes':
    scripts += ['misc/NwsService.py']

from distutils import core
kw = {
    'name': 'nwsserver',
    'version': '2.0.0',
    'author': 'REvolution Computing, Inc.',
    'author_email': 'sbweston@users.sourceforge.net',
    'url': 'http://nws-py.sourceforge.net/',
    'license': 'GPL version 2 or later',
    'description': 'Python NetWorkSpaces Server',
    'packages': ['nwss'],
    'scripts': scripts,
    'data_files': [
          (tacdir, ['misc/nws.tac']),
          (docdir, doc_files),
    ],
    'platforms': ['any'],
    'long_description': """\
NetWorkSpaces (NWS) is a system that makes it very easy
for different scripts and programs running (potentially) on
different machines to communicate and coordinate with one
another.

The requirements for the NWS server are:

  Python 2.2 or later on Linux, Mac OS X, and other Unix systems.
  Python 2.4 or later on Windows.
  Twisted 2.1 and Twisted-Web 0.5 or later.

  Twisted is available from:
      http://www.twistedmatrix.com/

  Twisted itself requires:
      Zope Interfaces 3.0.1 (http://zope.org/Products/ZopeInterface)""",
}

if (hasattr(core, 'setup_keywords') and 'classifiers' in core.setup_keywords):
    kw['classifiers'] = [
        'Topic :: System :: Clustering',
        'Topic :: System :: Distributed Computing',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Intended Audience :: System Administrators',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Natural Language :: English',
    ]

core.setup(**kw)
