#!/usr/bin/env/python2
from __future__ import print_function

import timeline
import argparse
import upstream_sync
import ConfigParser
import os
import logging
import subprocess

def debug(*args):
    logging.debug(*args)

TIMELINE_ROOT = None
MIRROR_ROOT = None

def make_parser():
    parser = argparse.ArgumentParser(description='Simple repository manager')
    parser.add_argument('-c', '--config', metavar='FILE', dest='config', default='/etc/repoman/repoman.conf')
    
    subparsers = parser.add_subparsers(dest='cmd')
    snap_create = subparsers.add_parser('snapshot-create', help='snapshot [source_snapshot]')
    snap_delete = subparsers.add_parser('snapshot-delete', help='snapshot')
    snap_rename = subparsers.add_parser('snapshot-rename', help='old_name new_name')
    snap_list = subparsers.add_parser('snapshot-list', help='-')
    snap_setlink = subparsers.add_parser('snapshot-link',  help='snapshot link_name')
    
    tline_create = subparsers.add_parser('timeline-create', help='name source_path')
    tline_delete = subparsers.add_parser('timeline-delete', help='name')
    tline_rename = subparsers.add_parser('timeline-rename', help='old_name new_name')
    tline_list = subparsers.add_parser('timeline-list', help='-')
    
    repo_list = subparsers.add_parser('repo-list', help='-')
    repo_sync = subparsers.add_parser('repo-sync', help='[glob1,glob2*]')
    
    
    for p in [snap_create, snap_delete, snap_rename, snap_list, snap_setlink]:
        p.add_argument('-t', '--timeline', metavar='TIMELINE', default='default', help='Timeline to operate on')
    
    snap_create.add_argument('name')
    snap_create.add_argument('source_snapshot', nargs='?', default=None, help="Source snapshot (defaults to latest)")
    snap_delete.add_argument('name')
    snap_rename.add_argument('old_name')
    snap_rename.add_argument('new_name')
    snap_setlink.add_argument('link')
    snap_setlink.add_argument('snapshot')
    
    tline_create.add_argument('name')
    tline_create.add_argument('source_path')


def real_path(path):
    if os.path.islink(path):
        raise ValueError("Path must not be a symbolic link: {0}".format(path))
    return os.path.realpath(path)


def snapshot_path(t, s):
    global TIMELINE_ROOT
    return os.path.normpath(os.path.join(TIMELINE_ROOT, t, s))


def timeline_path(t):
    global TIMELINE_ROOT
    return os.path.normpath(os.path.join(TIMELINE_ROOT, t))


def snapshot_exists(t, s):
    global TIMELINE_ROOT
    return os.path.exists(os.path.join(TIMELINE_ROOT, t, s))

def timeline_exists(t):
    global TIMELINE_ROOT
    return os.path.exists(os.path.join(TIMELINE_ROOT, t, '.timeline'))

def repo_sync(args):
    pass

def repo_list(args):
    pass

def snapshot_create(args):
    t = timeline.Timeline.load(timeline_path(args.timeline))
    if args.source_snapshot:
        print("Warning: source snapshots are not yet supported. Ignoring")
    t.create_named_snapshot(snapshot=args.name, source_snapshot=None)

def snapshot_refs(tl):
    t = timeline.Timeline.load(timeline_path(tl))
    tpath = timeline_path(tl)
    fs = os.listdir(tpath)
    refs = {}
    for f in fs:
        if os.path.isdir(os.path.join(tpath, f)):
            debug("Is dir: %s", f)
            refs[f] = ['self']
    for f in fs:
        fullpath = os.path.join(tpath, f)
        if os.path.islink(fullpath):
            debug("Is link: %s", f)
            link_target = os.path.realpath(fullpath)
            relpath = os.path.relpath(link_target, tpath)
            if not refs.get(relpath, False):
                print("Warning: Timeline {0} contains a link pointing outside the directory: {1} -> {2}".format(tl, f, link_target))
            else:
                refs[f].append(f)
    debug(refs)
    return refs

def snapshot_delete(args):
    global TIMELINE_ROOT
    t = timeline.Timeline.load(timeline_path(args.timeline))
    snap_path = snapshot_path(args.timeline, args.name)
    refs = snapshot_refs(args.timeline)
    if len(refs[args.name]) > 1:
        raise ValueError("Snapshot is referenced by links: {0}".format(refs[1:]))
    try:
        t.delete_snapshot(snapshot=args.name)
    except:
        if os.path.isdir(snapshot_path(args.timeline, args.name)):
            del_path = os.path.join(TIMELINE_ROOT, '_repoman_to_be_deleted')
            os.mkdir(del_path)
            os.rename(snap_path, os.path.join(del_path, args.name))
            subprocess.check_call(['rm', '-rf', del_path])
        else:
            raise ValueError("Snapshot not found")

	
def snapshot_rename(args):
    pass

def snapshot_link(args):
    pass

def unimplemented(args):
    print("Command {0} is currently not implemented".format(args.cmd))


def timeline_create(args):
    name = args.name
    if timeline_exists(name):
        raise ValueError("Timeline already exists")
    t = timeline.Timeline(name, real_path(args.source_path), timeline_path(name))
    debug("Creating timeline at %s from %s", timeline_path(name), real_path(args.source_path))
    t.save()

def timeline_list(args):
    p = timeline_path('')
    if not os.path.exists(timeline_path('')): return
    print("Timelines at {}:".format(p))
    for f in os.listdir(timeline_path('')):
        print(f)

def main():
    global TIMELINE_ROOT, MIRROR_ROOT
    args = parser.parse_args()
    config = ConfigParser.ConfigParser()
    config.read(args.config)
    MIRROR_ROOT = config.get('repoman', 'repoman_root')
    TIMELINE_ROOT = config.get('repoman', 'timeline_root')
    print(MIRROR_ROOT, TIMELINE_ROOT)
    print(args)

    return globals().get(args.cmd.replace('-','_'), unimplemented)(args)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
