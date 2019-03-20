#!/usr/bin/python -Ott
from __future__ import print_function

import sys
from optparse import OptionParser, OptionError
import subprocess
import os
import re
import ConfigParser
import getpass
import OpenSSL
import datetime
import glob
import fnmatch
import logging
import tempfile

logging.basicConfig()
logger = logging.getLogger('repoman.upstream_sync')


def make_dir(dir_path, mode=None):
    """ checks if a directory exists and create it if necessary
    :param mode: mode for makedirs
    :param dir_path: dir path for check

    :return: None
    """
    if not os.path.isdir(dir_path):
        # set current umask if not defined as parameter
        try:
            if mode:
                os.makedirs(dir_path, mode)
            else:
                os.makedirs(dir_path)
        except OSError as e:
            print("Failed to create directory", dir_path, e)
            sys.exit(1)


def build_yum_config(f, name, url, sslcacert, sslcert, sslkey, exclude):
    f.write('[main]\n')
    f.write('reposdir=/dev/null\n')
    f.write('deltarpm = 0\n')
    f.write('[{0}]\n'.format(name))
    f.write('name = {0}\n'.format(name))
    f.write('baseurl = {0}\n'.format(url))
    f.write('enabled = 1\n')
    f.write('gpgcheck = 0\n')

    if sslcacert and sslcert and sslkey:
        check_sslcert_expiration(sslcert)
        f.write('sslverify = 1\n')
        f.write('sslcacert = {0}\n'.format(sslcacert))
        f.write('sslclientcert = {0}\n'.format(sslcert))
        f.write('sslclientkey = {0}\n'.format(sslkey))

    if exclude:
        f.write('exclude = {0}\n'.format(exclude))

    f.write('metadata_expire = 60\n')
    f.flush()


def check_sslcert_expiration(sslcert):
    """checks to see if the ssl cert is going to expire soon"""
    try:
        cert = OpenSSL.crypto.load_certificate(
            OpenSSL.crypto.FILETYPE_PEM, file(sslcert).read())
        cert_expires = datetime.datetime.strptime(
            cert.get_notAfter(), "%Y%m%d%H%M%SZ")
    except IOError:
        return

    if datetime.datetime.now() > cert_expires:
        logger.warn('SSL Certificate (%s) expired on %s' %
                    (sslcert, cert_expires))
    elif datetime.datetime.now() + datetime.timedelta(days=14) > cert_expires:
        logger.warn('SSL Certificate (%s) is going to expire on %s' %
                    (sslcert, cert_expires))

    return


def get_auths(config):
    auths = dict()
    for title in config.sections():
        if title.startswith('auth/'):
            items = dict(config.items(title))
            auths[title[5:]] = items
    return auths


def match_filter(rfilter, title):
    """
    Match title against list of rfilters
    """
    if not rfilter:
        return True

    for f in rfilter:
        if fnmatch.fnmatch(title, f):
            return True
    return False


def match_synced(older_than, unsynced_only, repo):
    epoch = datetime.datetime.fromtimestamp(0)
    agelimit = datetime.datetime.now() - datetime.timedelta(days=older_than)
    ts = os.path.join(repo['path'], 'SYNC_TIMESTAMP')
    if os.path.exists(ts):
        st = os.stat(ts)
        mtime = datetime.datetime.fromtimestamp(st.st_mtime)
    else:
        mtime = epoch
    return (mtime > epoch and mtime < agelimit and not unsynced_only) or (mtime == epoch)


def filter_repos(repos, config):
    res = []
    for repo in repos:
        if not match_filter(config.filters, repo["name"]):
            continue
        if not match_synced(config.older_than, config.unsynced_only, repo):
            continue
        res.append(repo)
    return res


def config_repos(config, args):
    """
    parse configuration files and return repos.

    if rfilter is set, only repos that match rfilter will be returned
    """

    defaults = {
        'copylinks': 'False',
        'exclude': '',
    }
    repoconfig = ConfigParser.ConfigParser(defaults)
    repoconfig.read(glob.glob(os.path.join(
        config.get('repoman', 'repoconf_dir'), '*.repo')))

    auths = get_auths(config)

    # sort all the repos by alpha order, ConfigParser return sections
    # in the order that they appear in the config file
    repos = []
    for title in repoconfig.sections():
        repo = dict(repoconfig.items(title))
        if 'createrepo' in repo:
            repo['createrepo'] = repoconfig.getboolean(title, 'createrepo')
        repo['name'] = title
        repo['path'] = os.path.join(config.get('repoman', 'mirror_root'), repo[
                                    'path'])  # absolute path of repository
        if 'auth' in repo:
            repo['auth'] = auths[repo['auth']]
        repos.append(repo)

    repos = sorted(repos, key=lambda k: k['name'])

    return filter_repos(repos, args)


def sync_cmd_reposync(repo, keep_deleted, newest_only, verbose):
    sslcacert = None
    sslcert = None
    sslkey = None
    exclude = None

    reposync_opts = []

    name = repo['name']
    url = repo['url']
    path = os.path.abspath(repo['path'])

    if repo.has_key('auth'):
        auth = repo['auth']
        sslcacert = auth['sslcacert']
        sslcert = auth['sslcert']
        sslkey = auth['sslkey']

    if repo.has_key('exclude'):
        exclude_list = repo['exclude'].split(',')
        # split() will return an empty list element
        if exclude_list:
            exclude = ' '.strip().join(exclude_list)

    yum_conf = tempfile.NamedTemporaryFile(prefix='repoman.tmp', delete=True)
    tmppath = yum_conf.name
    build_yum_config(yum_conf, name, url, sslcacert, sslcert, sslkey, exclude)

    reposync_opts.extend(('-c', tmppath))
    reposync_opts.extend(('-r', name))
    if not keep_deleted:
        reposync_opts.append('--delete')
    reposync_opts.extend(('-p', path))

    # detect arch
    match_arch = re.match(
        r'.*(?:/|-)(ppc64|ppc64le|x86_64|i386|i686|armhfp|amd64|x86|aarch64)(?:/|$)', url)
    # detect a mirror of srpms(so .src.rpm files will get mirrored), See
    # --source option to reposync
    match_source = re.match(r'.*(?:/|-)(srpms|SRPMS)(?:/|$)', url)
    if match_arch:
        arch = match_arch.groups()[0]
        if arch in ['i386', 'x86']:
            arch = 'i686'
        elif arch in ['amd64', 'x86_64']:
            arch = 'x86_64'
        reposync_opts.extend(('--arch', arch))

    if match_source:
        reposync_opts.extend(('--source', ))

    if not (match_arch or match_source):
        logger.warn('unable to detect architecture for %s' % name)

    # build options
    if repo.has_key('sync_opts'):
        opt_list = repo['sync_opts'].split()
        for opt in opt_list:
            reposync_opts.append(opt)
    else:
        reposync_opts.append('--tempcache')
        reposync_opts.append('--norepopath')
        reposync_opts.append('--downloadcomps')
        if newest_only:
            reposync_opts.append('--newest-only')

    # be quiet if verbose is not set
    if not verbose:
        reposync_opts.append('-q')

    sync_cmd = ['reposync'] + reposync_opts
    return (yum_conf, sync_cmd)


def sync_cmd_dnf(repo, keep_deleted, newest_only, verbose):
    sslcacert = None
    sslcert = None
    sslkey = None
    exclude = None

    dnf_opts = ['--disablerepo=*', '--refresh']

    name = repo['name']
    url = re.sub('^dnf::', '', repo['url'])
    path = os.path.abspath(repo['path'])
    dnf_reponame = os.path.basename(path)

    if repo.has_key('auth'):
        auth = repo['auth']
        dnf_opts.append('--setopt=sslcacert={}'.format(auth['sslcacert']))
        dnf_opts.append('--setopt=sslclientcert={}'.format(auth['sslcert']))
        dnf_opts.append('--setopt=sslclientkey={}'.format(auth['sslkey']))

    if repo.has_key('exclude'):
        dnf_opts.extend(('-x', repo['exclude']))

    dnf_opts.extend(('--repofrompath', '{0},{1}'.format(dnf_reponame, url)))

    if repo.has_key('sync_opts'):
        opt_list = repo['sync_opts'].split()
        for opt in opt_list:
            dnf_opts.append(opt)

    # be quiet if verbose is not set
    if not verbose:
        dnf_opts.append('-q')

    sync_cmd = ['dnf'] + dnf_opts + ['reposync', '-p', os.path.dirname(path)]
    return sync_cmd


def sync_cmd_rhnget(repo):
    systemid = os.path.join(os.path.split(repo['path'])[0], 'systemid')
    if not os.path.isfile(systemid):
        logger.warn("rhn: can not find systemid (%s)" % systemid)
        return

    sync_cmd = ['rhnget', '-q', '-s', systemid, repo['url'], repo['path']]
    return sync_cmd


def sync_cmd_rsync(repo, keep_deleted, verbose):
    try:
        username = repo['auth']['user']
    except KeyError:
        url = repo['url']
    else:
        s = repo['url'].split('//', 1)
        s.insert(1, '//{0}@'.format(username))
        url = ''.join(s)

    try:
        password = repo['auth']['password']
    except KeyError:
        password = ''

    logger.debug('set RSYNC_PASSWORD environment variable')
    os.environ["RSYNC_PASSWORD"] = password

    rsync_opts = []
    # build options
    if repo.has_key('sync_opts'):
        opt_list = repo['sync_opts'].split()
        for opt in opt_list:
            rsync_opts.append(opt)
    else:
        rsync_opts.append('--no-motd')
        rsync_opts.append('--recursive')
        if not keep_deleted:
            rsync_opts.append('--delete')
        rsync_opts.append('--times')
        rsync_opts.append('--contimeout=30')

    if repo['copylinks'].lower() == 'true':
        rsync_opts.append('--copy-links')

    exclude_list = repo['exclude'].split(',')
    for item in exclude_list:
        # split() will return an empty list element
        if item:
            rsync_opts.append('--exclude')
            rsync_opts.append(item)

    if verbose:
        rsync_opts.append('--itemize-changes')

    sync_cmd = ['rsync'] + rsync_opts + [url, repo['path']]
    return sync_cmd


def sync_cmd_you(repo):
    # checking for sles credentials
    deviceid = os.path.join(sles_auth_cred_dir, 'deviceid')
    secret = os.path.join(sles_auth_cred_dir, 'secret')

    if not os.path.isfile(deviceid):
        logger.warn("you: can not find deviceid file (%s)" % deviceid)
        return
    elif not os.path.isfile(secret):
        logger.warn('you: can not find secret file (%s)' % secret)
        return

    url = re.sub('^you://', 'https://', repo['url'])
    sync_cmd = ['/opt/bin/youget', '-q', '--source', '-d',
                sles_auth_cred_dir, '--delete', url, repo['path']]

    return sync_cmd


def list_repos(config, args):
    repos = config_repos(config, args)
    print("{0:<25} {1:<25} {2:35}".format("REPO", "LAST_SYNC", "SOURCE"))
    for repo in sorted(repos):
        ts = os.path.join(repo['path'], 'SYNC_TIMESTAMP')
        if os.path.exists(ts):
            st = os.stat(ts)
            mtime = datetime.datetime.fromtimestamp(st.st_mtime)
            synced = mtime.strftime("%Y.%m.%d-%H:%M:%S")
        else:
            synced = "Never"
        print("{0:<25} {1:<25} {2:35}".format(repo["name"], synced, repo["url"]))


def sync_repos(config, args):
    if args.verbose:
        logger.setLevel(level=logging.DEBUG)
    else:
        logger.setLevel(level=logging.WARNING)

    createrepo_default = config.getboolean('repoman', 'createrepo_after_sync')
    createrepo_cache_root = config.get('repoman', 'createrepo_cache_root')
    createrepo_exec = [config.get('repoman', 'createrepo_bin')]
    keep_deleted = config.getboolean('repoman', 'sync_keep_deleted')
    newest_only = config.getboolean('repoman', 'newest_only')
    tmp_dir = config.get('repoman', 'tmp_dir')

    repos = config_repos(config, args)
    for repo in repos:
        # set variables based on values in config
        url = repo['url']
        name = repo['name']
        createrepo = repo.get('createrepo', createrepo_default)
        path = os.path.abspath(repo['path'])  # absolute path of repository

        # create repo directory
        make_dir(path, 0775)

        if len(createrepo_cache_root.strip()) > 0:
            createrepo_cache = os.path.join(
                createrepo_cache_root, repo['name'] + '.cache')
        else:
            createrepo_cache = os.path.join(repo['path'], ".cache")

        createrepo_cache = os.path.abspath(createrepo_cache)

        # Generate the sync and createrepo commands to be used based on
        # repository type
        createrepo_opts = ['--pretty', '--database',
                           '--update', '--cachedir', createrepo_cache, path]
        if not args.verbose:
            createrepo_opts.append('-q')

        # if comps.xml exists, use it to generate group data
        comps_file = os.path.join(path, 'comps.xml')
        if os.path.isfile(comps_file):
            createrepo_opts = ['-g', comps_file] + createrepo_opts

        createrepo_cmd = createrepo_exec + createrepo_opts
        tmpfile = None

        if re.match('^(http|https|ftp)://', url):
            tmpfile, sync_cmd = sync_cmd_reposync(repo, keep_deleted, newest_only, args.verbose)
        elif re.match('^dnf::(http|https|ftp)://', url):
            sync_cmd = sync_cmd_dnf(repo, keep_deleted, newest_only, args.verbose)
        elif re.match('^rhns:///', url):
            sync_cmd = sync_cmd_rhnget(repo)
        elif re.match('^you://', url):
            sync_cmd = sync_cmd_you(repo)
        elif re.match('^rsync://', url):
            sync_cmd = sync_cmd_rsync(repo, keep_deleted, args.verbose)
        else:
            logger.warn('url type unknown - %s' % url)
            continue

        if not sync_cmd:
            continue

        if args.dry_run:
            print("Would execute: ", " ".join(sync_cmd))
            if createrepo:
                print("Would execute: ", " ".join(createrepo_cmd))
            continue

        # preform sync - rhnget/rsync
        logger.info('syncing %s' % name)
        if args.verbose:
            stdout_pipe = sys.stdout
            stderr_pipe = sys.stderr
        else:
            stdout_pipe = subprocess.PIPE
            stderr_pipe = subprocess.STDOUT

        p1 = subprocess.Popen(sync_cmd, stdout=stdout_pipe,
                              stderr=stderr_pipe, stdin=subprocess.PIPE)
        p1_rc = p1.wait()
        if tmpfile:
            tmpfile.close()
        stdout, _ = p1.communicate()

        # display output if the sync fails
        if p1_rc > 0:
            if not args.verbose:
                logger.warn(stdout)
            logger.warn('sync failed: %s' % name)
            continue  # no need to run createrepo if sync failed

        # run createrepo to generate package metadata
        update_stamp = True
        if createrepo:
            logger.info('generating package metadata: {0}'.format(name))

            p2 = subprocess.Popen(
                createrepo_cmd, stdout=stdout_pipe, stderr=stderr_pipe, stdin=subprocess.PIPE)
            p2_rc = p2.wait()
            stdout, _ = p2.communicate()

            if p2_rc > 0:
                if not args.verbose:
                    logger.warn(stdout)
                logger.warn('createrepo failed: %s' % name)
                update_stamp = False

        if update_stamp and os.path.isdir(path):
            subprocess.call(["touch", os.path.join(path, "SYNC_TIMESTAMP")])
