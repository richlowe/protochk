#!/usr/bin/env python3
#
# This file and its contents are supplied under the terms of the
# Common Development and Distribution License ("CDDL"), version 1.0.
# You may only use this file in accordance with the terms of version
# 1.0 of the CDDL.
#
# A full copy of the text of the CDDL should have accompanied this
# source.  A copy of the CDDL is also available via the Internet at
# http://www.illumos.org/license/CDDL.
#

# Copyright 2023 Richard Lowe

import fnmatch
import getopt
import os
import sys

class ExceptionParseError(Exception):
    pass

class ExceptionList:
    """An exception list is a file composed of rules, one per line, blank
    lines, or comment lines.

    Comments have a "#" character as the first in a line.  Rules are one of
    the tokens "IGNORE_HEADER", "IGNORE_TARGET", "IGNORE_DIR", followed by a
    pattern to match.

    IGNORE_HEADER takes an glob pattern to ignore a given headers use (which
    will be interpreted relative to the sysroot if any).

    IGNORE_DIR takes a glob pattern to ignore any problems in a given
    directory, relative to the current directory which is assumed to the
    workspace root.

    IGNORE_TARGET takes an absolute directory followed by a : and a pattern to
    match against the make target, to ignore specific targets in a given
    directory.
    """
    def __init__(self, path, sysroot=None):
        self.ignore_headers = set()
        self.ignore_targets = set()
        self.ignore_dirs = set()

        for (n, line) in enumerate(open(path, 'r')):
            line = line.strip()
            if not line:
                continue

            if line.startswith('#'):
                continue

            try:
                rule, ignpath = line.split()
            except Exception:
                raise ExceptionParseError(f"{path}: {n+1}: "
                                          f"malformed line: '{line}'")

            if rule == 'IGNORE_HEADER':
                if sysroot:
                    ignpath = os.path.join(sysroot, ignpath.lstrip('/'))
                    self.ignore_headers.add(ignpath)
                self.ignore_headers.add(ignpath)
            elif rule == 'IGNORE_TARGET':
                self.ignore_targets.add(ignpath)
            elif rule == 'IGNORE_DIR':
                self.ignore_dirs.add(ignpath)
            else:
                raise ExceptionParseError(f"{path}: {n+1}: "
                                          f"unknown rule: {rule}")

    def match(self, dir, target, header):
        for elt in self.ignore_headers:
            if header.startswith(elt) or fnmatch.fnmatch(header, elt):
                return True
        for elt in self.ignore_dirs:
            if dir.startswith(elt) or fnmatch.fnmatch(dir, elt):
                return True
        for elt in self.ignore_targets:
            idir, itarget = elt.split(':')
            if idir == dir and fnmatch.fnmatch(target, itarget):
                return True
        return False

def usage():
    sys.stderr.write(f"Usage: {os.path.basename(sys.argv[0])} "
                     "-w <workspace> [-e exceptions] "
                     "[-s sysroot] files...\n")
    sys.exit(2)

def main(args):
    """Parse (loosely) the .make.state files on the command line, and display
    the path, target, and any dependencies found outside of the workspace
    root.

    -e <except list>	- a file containing exceptions to not display
    -w <workspace>	- specify the root of the workspace we're checking
    -s <sysroot>	- a sysroot the exception list should be interpretted
    			  relative to.
    """
    workspace = os.getenv("CODEMGR_WS")
    exception_list = None
    sysroot = None
    exc_path = None

    try:
        opts, args = getopt.getopt(args, 'e:s:w:')
    except getopt.GetoptError as e:
        sys.stderr.write(str(e) + '\n')
        usage()

    for opt, arg in opts:
        if opt == '-e':
            exc_path = arg
        elif opt == '-s':
            sysroot = arg
        elif opt == '-w':
            workspace = arg

    if not workspace:
        sys.stderr.write("-w not specified and CODEMGR_WS unset\n")
        usage()

    try:
        exception_list = ExceptionList(exc_path, sysroot=sysroot)
    except Exception as e:
        sys.stderr.write(str(e) + '\n')
        sys.exit(1)

    for statefile in args:
        f = None

        try:
            f = open(statefile, 'r')
        except Exception as e:
            sys.stderr.write(str(e) + '\n')
            sys.exit(1)

        # The syntax of these files is that of a Makefile, but we make
        # simplifying assumptions that there are no continuation lines etc.
        #
        # Skip any line that begins with a tab, for any other line, any
        # white-space separated content after a colon (:) is a dependency
        # list.
        #
        # Of those, we form a full path, and form a set of paths outside of
        # the workspace specified by -w or $CODEMGR_WS to complain about.
        #
        # We only check header files suffixed by '.h', as ld(1)'s -z
        # assertdeflib covers libraries, and does so much more conveniently.
        hits = {}
        for line in open(statefile, 'r'):
            if line.startswith('\t') or not line.find(':'):
                continue

            targets, dependencies = line.split(':')
            for path in dependencies.split(' '):
                path = path.strip()

                if not path.endswith('.h'):
                    continue

                if not path.startswith(os.path.sep):
                    path = os.path.join(os.path.dirname(statefile), path)
                    path = os.path.realpath(path)

                if not path.startswith(workspace):
                    if targets in hits:
                        hits[targets].add(path)
                    else:
                        hits[targets] = set([path])

        for target, paths in hits.items():
            for path in paths:
                dir = os.path.dirname(statefile)
                path = os.path.realpath(path)
                if not exception_list.match(dir, target, path):
                    print(f"{dir}: {target}: {path}")

if __name__ == '__main__':
    main(sys.argv[1:])
