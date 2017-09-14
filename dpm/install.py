import json
import os
import requests
import tempfile
import platform
import re
import sys
import progressbar
import shutil
import subprocess
import shlex
import yaml
import rfc3987
from distutils.version import LooseVersion
from .utils import *
from .uninstall import uninstall_package
from contextlib import closing
import zipfile
import glob
import logging
import traceback

class InstallError(Exception):
    def __str__(self):
        return 'InstallError: ' + Exception.__str__(self)

temp = []
packages = []

def install(args):
    try:
        packages.extend(args.package)
        del args.package
        while packages:
            package = packages.pop(0)
            log.info('Installing %s'%package)
            install_package(package, **vars(args))
        log.info('Success')
    except InstallError as e:
        log.debug(traceback.format_exc())
        log.error(str(e))
        sys.exit(1)
    finally:
        cleanup()

parser = subparsers.add_parser('install', help='install package(s)')
parser.set_defaults(func=install)
parser.add_argument('package', nargs='+')
parser.add_argument('-v', '--verbose', action='store_true', help="detailed output")
parser.add_argument('-u', '--update', action='store_true', help="update installation")
parser.add_argument('-f', '--force', action='store_true', help="force install")

def install_state(name, release, update, force):
    other_info = get_package_yaml(name, 'package.yaml')
    if other_info:
        if not force:
            if other_info['release'] == release:
                log.info('Package %s already installed', name)
                return 1
            if not update:
                raise InstallError('Package %s already installed\n'
                    'Use --update to install new release', name)
        return -1
    return 0


def install_package(package, force = False,
        update = False, **kwargs):

    if not os.path.exists(package):
        try:
            rfc3987.parse(package, rule='IRI')
        except ValueError:
            name, release, machine = info_from_name(package)
            if release == 'latest':
                # query server for latest release
                raise InstallError('Not implemented')
            status = install_state(name, release, update, force)
            if status > 0:
                return
            for i, v in enumerate(packages):
                if os.path.exists(v):
                    with closing(zipfile.ZipFile(v, 'r')) as z:
                        with closing(z.open('package.yaml', 'r')) as f:
                            info = yaml.load(f)
                            if info['name'] == name and \
                                    info['release'] == release:
                                package = packages.pop(i)
                                break
            else:
                # download actual package
                raise InstallError('Not implemented')
        else:
            target_dir = tempfile.mkdtemp('-dpm')
            temp.append(target_dir)
            package = download(target_dir, package)



    with open(package, 'rb') as f:
        z = zipfile.ZipFile(f, 'r')

        with closing(z.open('package.yaml', 'r')) as y:
            package_info = yaml.load(y)

        with closing(z.open('install.yaml', 'r')) as y:
            install_info = yaml.load(y)

        status = install_state(package_info['name'], package_info['release'], update, force)

        if status > 0:
            return

        deps = install_info.get('dependencies')
        if deps:
            log.info('Package %s depends on:\n%s\nInstalling...'%(package_info['name'],
                '\n'.join(deps)))
            for v in deps:
                install_package(v, update = update)

        install_path = get_install_path(package_info['name'])

        log.debug('installing to: %s', install_path)

        if status < 0:
            uninstall_package(package_info['name'], other_deps = deps)

        install_list = []
        if not os.path.exists(install_path):
            os.makedirs(install_path)
            install_list.append(install_path)

        package_path = tempfile.mkdtemp('-dpm')
        temp.append(package_path)

        files = install_info.get('files', ())
        log.debug('Exctracting archive to: %s', package_path)

        for name in z.namelist():
            log.debug('Exctracting: %s', name)
            files.append(name)
            z.extract(name, package_path)

        end = z.infolist()[0].header_offset

        _seek = f.seek
        def seek_hook(offset, whence = 0):
            if whence == 2:
                offset = end + offset
                whence = 0
            _seek(offset, whence)
        f.seek = seek_hook
        _read = f.read
        def read_hook(size = -1):
            if size == -1:
                size = end - f.tell()
            return _read(size) 
        f.read = read_hook
        y = z
        z = zipfile.ZipFile(f, 'r')
        for name in z.namelist():
            log.debug('Exctracting: %s', name)
            z.extract(name, package_path)

    variables = dict(
            source=package_path,
            dest=install_path,
            python=sys.executable,
            platform=platform_name,
            arch=platform_arch,
            system=system_name
        )

    for v in install_info.get('pre_install', ()):
        if not run_process(command=v, cwd=package_path, format_kwargs=variables):
            raise InstallError('Pre-install command error.')

    for v in files:
        for item in glob.iglob(os.path.join(package_path, v)):
            path_rel = os.path.relpath(item, package_path)
            install_to = os.path.join(install_path, path_rel)
            install_list.append(install_to)
            if os.path.isdir(item):
                for root, dirnames, filenames in os.walk(item):
                    for name in dirnames + filenames:
                        path = os.path.join(root, name)
                        path_rel = os.path.relpath(path, package_path)
                        install_list.append(os.path.join(install_path, path_rel))
            log.debug('installing: %s', install_to)
            shutil.move(item, install_to)

    for v in install_info.get('post_install', ()):
        if not run_process(command=v, cwd=package_path, format_kwargs=variables):
            raise InstallError('Post-install command error.')

    if deps:
        for v in deps:
            name = info_from_name(v)[0]
            deps_list = get_package_list(name, 'deps.txt')
            if package_info['name'] not in deps_list:
                deps_list.append(package_info['name'])
                save_package_list(name, 'deps.txt', deps_list)

    install_list.append(os.path.join(install_path, 'deps.txt'))
    install_list.append(os.path.join(install_path, 'files.txt'))

    save_package_list(package_info['name'], 'deps.txt', [])
    save_package_list(package_info['name'], 'files.txt', install_list)

def cleanup():
    log.info('Cleanup')
    for folder in temp:
        log.debug('Removing %s', folder)
        shutil.rmtree(folder)
