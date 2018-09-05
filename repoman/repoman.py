#!/usr/bin/env/python2
from __future__ import print_function

import timeline
import argparse
import upstream_sync
import ConfigParser
import os
import pwd
import grp
import logging
import subprocess
from sys import exit

logging.basicConfig()


def debug(*args):
    logging.debug(*args)

TIMELINE_ROOT = None
MIRROR_ROOT = None


def make_parser():
    parser = argparse.ArgumentParser(description='Simple repository manager')

    parser.add_argument('-c', '--config', metavar='FILE',
                        dest='config', default='/etc/repoman/repoman.conf')

    subparsers = parser.add_subparsers(dest='cmd')
    snap_create = subparsers.add_parser(
        'snapshot-create', help='snapshot [source_snapshot]')
    snap_delete = subparsers.add_parser('snapshot-delete', help='snapshot')
    snap_rename = subparsers.add_parser(
        'snapshot-rename', help='old_name new_name')
    snap_list = subparsers.add_parser('snapshot-list', help='-')
    link_set = subparsers.add_parser('link-set',  help='link_name snapshot')
    link_delete = subparsers.add_parser('link-delete', help='link')
    link_list = subparsers.add_parser('link-list', help='-')

    tline_create = subparsers.add_parser(
        'timeline-create', help='name source_path')
    tline_delete = subparsers.add_parser('timeline-delete', help='name')
    tline_rename = subparsers.add_parser(
        'timeline-rename', help='old_name new_name')
    tline_list = subparsers.add_parser('timeline-list', help='-')
    tline_show = subparsers.add_parser('timeline-show', help='timeline')

    repo_list = subparsers.add_parser('repo-list', help='-')
    repo_sync = subparsers.add_parser('repo-sync', help='[glob1] [glob2] ...')

    for p in [snap_create, snap_delete, snap_rename, snap_list, link_set, link_delete, link_list]:
        p.add_argument('-t', '--timeline', metavar='TIMELINE',
                       default='default', help='Timeline to operate on')

    snap_create.add_argument('name', nargs='?', default=None,
                             help="Snapshot name (or create an auto-rotating one if not specified)")
    snap_create.add_argument('-s', '--source-snapshot', nargs='?',
                             default=None, help="Source snapshot (defaults to latest)")

    snap_delete.add_argument('name')

    snap_rename.add_argument('old_name')
    snap_rename.add_argument('new_name')

    link_set.add_argument('link_name')
    link_set.add_argument('snapshot', nargs='?', default=None)
    link_set.add_argument('--max-offset', default=None, type=int)

    tline_create.add_argument('name')
    tline_create.add_argument('source_path')
    tline_delete.add_argument('timeline')

    tline_show.add_argument('timeline')
    repo_list.add_argument('filters', nargs='*', default=None,
                           help="list of globs to match")
    repo_sync.add_argument('filters', nargs='*', default=None,
                           help="list of globs to match")
    repo_sync.add_argument(
        '--dry-run', '-n', action='store_true', default=False)

    for p in [repo_sync, repo_list]:
        p.add_argument('-o', '--older-than', default=0, type=int, metavar='DAYS',
                       help="Act on repos not synced in DAYS days")
        p.add_argument('-u', '--unsynced-only', action='store_true', default=False, help="Act on unsynced repos")

    for p in [snap_create, snap_delete, snap_rename, snap_list, link_set, link_delete, link_list, tline_create, tline_delete, tline_rename, tline_list, tline_show, repo_list, repo_sync]:
        p.add_argument('--verbose', '-v', action='store_true', default=False)

    return parser


def switch_user(config):
    wanted_uid = pwd.getpwnam(config.get('repoman', 'user')).pw_uid
    wanted_gid = grp.getgrnam(config.get('repoman', 'group')).gr_gid

    if os.getuid() == wanted_uid:
        return

    if os.getuid() != 0:
        raise Exception("You must run this as root or", config.get('repoman', 'user'))

    os.setgroups([])
    os.setgid(wanted_gid)
    os.setuid(wanted_uid)


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


def get_timeline(args):
    return timeline.Timeline.load(timeline_path(args.timeline))


def snapshot_exists(t, s):
    global TIMELINE_ROOT
    return os.path.exists(os.path.join(TIMELINE_ROOT, t, s))


def timeline_exists(t):
    global TIMELINE_ROOT
    return os.path.exists(os.path.join(TIMELINE_ROOT, t, '.timeline'))

# ACTUAL COMMANDS START HERE


def unimplemented(args, config):
    print("Command {0} is currently not implemented".format(args.cmd))


def repo_sync(args, config):
    switch_user(config)
    upstream_sync.sync_repos(config, args)
    pass


def repo_list(args, config):
    print("Repositories defined in {0}:".format(
        config.get('repoman', 'repoconf_dir')))
    upstream_sync.list_repos(config, args)


def snapshot_create(args, config):
    switch_user(config)
    t = get_timeline(args)
    if not args.name:
        t.create_snapshot()
    else:
        t.create_named_snapshot(snapshot=args.name, source_snapshot=args.source_snapshot)


def snapshot_delete(args, config):
    global TIMELINE_ROOT
    switch_user(config)
    t = timeline.Timeline.load(timeline_path(args.timeline))
    snap_path = snapshot_path(args.timeline, args.name)
    t.delete_snapshot(snapshot=args.name)

# snapshot_rename


def snapshot_list(args, config):
    t = get_timeline(args)
    t.print_snapshots()


def timeline_delete(args, config):
    t = get_timeline(args)
    print("To delete the timeline, simply run rm -rf '{0}'".format(timeline_path(args.timeline)))


def timeline_create(args, config):
    switch_user(config)
    name = args.name
    if timeline_exists(name):
        raise ValueError("Timeline already exists")
    t = timeline.Timeline(name, real_path(
        args.source_path), timeline_path(name))
    debug("Creating timeline at %s from %s",
          timeline_path(name), real_path(args.source_path))
    t.save()


def timeline_list(args, config):
    p = timeline_path('')
    if not os.path.exists(timeline_path('')):
        return
    print("Timelines at {}:".format(p))
    for f in os.listdir(timeline_path('')):
        print(f)


def timeline_show(args, config):
    t = get_timeline(args)
    print(t)


# link_set
def link_set(args, config):
    switch_user(config)
    t = get_timeline(args)
    t.create_link(link=args.link_name, snapshot=args.snapshot, max_offset=args.max_offset)


def link_delete(args, config):
    switch_user(config)
    t = get_timeline(args)
    t.delete_link(args.link_name)


def link_list(args, config):
    t = get_timeline(args)
    t.print_links()

# END OF COMMANDS


def main():
    config_defaults = {
        'repoconf_dir': '/etc/repoman/repos.d',
        'tmp_dir': '/var/tmp/repoman',
        'createrepo_after_sync': 'true',
        # Defaults to ${repo_mirror_dir}/.cache
        'createrepo_cache_root': '',
        'createrepo_bin': 'createrepo_c',
        'sync_keep_deleted': 'false',
    }

    global TIMELINE_ROOT, MIRROR_ROOT
    parser = make_parser()
    args = parser.parse_args()
    config = ConfigParser.ConfigParser(config_defaults)
    config.read(args.config)

    MIRROR_ROOT = config.get('repoman', 'mirror_root')
    TIMELINE_ROOT = config.get('repoman', 'timeline_root')

    try:
        return globals().get(args.cmd.replace('-', '_'), unimplemented)(args, config)
    except Exception as e:
        if args.verbose:
            import traceback
            traceback.print_exc()
        else:
            print("Error:", e)
        exit(1)


if __name__ == '__main__':
    main()
