
import zipfile
from .utils import *
import fnmatch
import glob
import io
import os
import yaml
from contextlib import closing
import logging
import sys
from pkgutil import iter_modules
from importlib.machinery import ExtensionFileLoader
import base64
from struct import pack, unpack, calcsize
from itertools import cycle
from .install import install_package
import shlex
import rfc3987
import tempfile
import shutil

class BuildError(Exception):
    def __str__(self):
        return 'BuildError: ' + Exception.__str__(self)

temp = []

def build(args):
    try:
        try:
            rfc3987.parse(args.path, rule='IRI')
        except ValueError:
            if os.path.isfile(args.path):
                source_arc = args.path
            else:
                source_arc = None
        else:
            target_dir = tempfile.mkdtemp('-dpm')
            temp.append(target_dir)
            source_arc = download(target_dir, args.path)

        if source_arc:
            source_dir = tempfile.mkdtemp('-dpm')
            temp.append(source_dir)
            log.debug('extracting %s', source_arc)
            with zipfile.ZipFile(source_arc) as z:
                z.extractall(source_dir)
            for v in os.listdir(source_dir):
                source_dir = os.path.join(source_dir, v)
                break
        else:
            source_dir = args.path

        with open(os.path.join(source_dir, 'package.yaml'), 'r') as f:
            package_info = yaml.load(f)

        install_info = {}

        info_files = list(args.spec)

        keywords = (
            'targets',
            'extras',
            'ignore',
            'pre_build',
            'pre_install',
            'post_install',
            'pre_uninstall',
            )

        sections = (
            system_name,
            platform_arch,
            platform_name,
        )

        def load_install_info(path, data=None):
            if data is None:
                with open(path, 'r') as f:
                    data = yaml.load(f)
            include = data.get('include')
            if include:
                if not isinstance(include, list):
                    include = [include]
                for v in include:
                    load_install_info(os.path.join(os.path.dirname(path), v))
            
            for k, v in data.items():
                if k in keywords:
                    if not isinstance(v, list):
                        v = [v]
                    install_info[k] = install_info.setdefault(k, []) + v
            for k in sections:
                if k in data:
                    load_install_info(path, data[k])

        for v in args.spec:
            path = os.path.join(source_dir, v)
            load_install_info(path)

        if args.print_spec:
            print(yaml.dump(install_info,
                default_flow_style=False))
            return

        variables = dict(
            path=source_dir,
            python=sys.executable,
            platform=platform_name,
            arch=platform_arch,
            system=system_name
        )

        if not args.skip_pre_build:
            for v in install_info.get('pre_build', ()):
                if not run_process(command=v, cwd=source_dir, format_kwargs=variables):
                    raise BuildError('Pre-build command error.')

        info = {}
        binaries = {}

        package_name = package_info['name'].replace('/', '-')
        platform = args.platform or platform_name
        filename = '%s-%s-%s.zip'%(package_name, package_info['release'], platform)

        if args.out:
            if not os.path.exists(args.out):
                os.makedirs(args.out)
            filename = os.path.join(args.out, filename)
        elif args.install:
            target_dir = tempfile.mkdtemp('-dpm')
            temp.append(target_dir)
            filename = os.path.join(target_dir, filename)

        ignore = [os.path.normpath(v) for v in install_info.pop('ignore', ())]
        ignore.append('package.yaml')
        for v in args.spec:
            ignore.append(v)
        ignore.append(filename)

        def is_ignored(path):
            path = os.path.relpath(path, source_dir)
            for patt in ignore:
                if fnmatch.fnmatch(path, patt):
                    return True

        files = install_info.get('targets', [])
        extras = install_info.pop('extras', [])

        log.debug('Writing %s', filename)

        with closing(zipfile.ZipFile(filename, 'w')) as z:

            def write_zip(path):
                log.debug('written: %s', path)
                arcname = os.path.relpath(path, source_dir)
                z.write(path, arcname)

            for v in files + extras:
                for item in glob.iglob(os.path.join(source_dir, v)):
                    if os.path.isdir(item):
                        for root, dirnames, filenames in os.walk(item, topdown=True):
                            if not is_ignored(os.path.relpath(root, source_dir)):
                                write_zip(root)
                                for fname in filenames:
                                    fpath = os.path.join(root, fname)
                                    if not is_ignored(os.path.relpath(fpath, source_dir)):
                                        write_zip(fpath)
                                    else:
                                        log.debug('ignored: %s', fpath)
                            else:
                                log.debug('ignored: %s', root)
                                dirnames[:] = []
                    elif not is_ignored(os.path.relpath(item, source_dir)):
                        write_zip(item)
                    else:
                        log.debug('ignored: %s', item)

        addon = io.BytesIO()
        with zipfile.ZipFile(addon, 'w') as z:
            log.debug('written: %s', os.path.join(source_dir, 'package.yaml'))
            z.write(os.path.join(source_dir, 'package.yaml'), 'package.yaml')
            install_bytes = yaml.dump(install_info,
                default_flow_style=False).encode('utf-8')
            log.debug('written: %s', 'install.yaml')
            z.writestr('install.yaml', install_bytes)
            for k, v in binaries.items():
                arcname = os.path.relpath(k, source_dir)
                log.debug('saving binary: '+arcname)
                z.writestr(arcname, v)

        if args.split:
            fname, ext = os.path.splitext(filename)
            filename = fname + '_2.' + ext
            with open(filename, 'wb') as z:
                z.write(addon.getvalue())
        else:
            with open(filename, 'ab') as z:
                z.write(addon.getvalue())
        
        if args.install:
            install_package(filename, force=args.force, upgrade=args.upgrade)

        log.info('Success')

    except BuildError as e:
        log.error(e)
        sys.exit(1)
    except:
        raise
    finally:
        cleanup()

def cleanup():
    log.info('Cleanup')
    for folder in temp:
        log.debug('Removing %s', folder)
        shutil.rmtree(folder)

parser = subparsers.add_parser('build', help='build package')
parser.set_defaults(func=build)

parser.add_argument('path', help="specify directory of package sources")
parser.add_argument('-v', '--verbose', action='store_true', help="detailed output")
parser.add_argument('-o', '--out', help='Output folder')
parser.add_argument('-s', '--spec', nargs = '*', default=['install.yaml'], help='The "yaml" files with package specification')
parser.add_argument('--platform', help="Platform for new package")
parser.add_argument('--print-spec', action='store_true', help="Prints specs merge result and exit")
parser.add_argument('--skip-pre-build', action='store_true', help="Skip running pre-build commands")
parser.add_argument('-u', '--upgrade', action='store_true', help="upgrade installation")
parser.add_argument('-f', '--force', action='store_true', help="force install")

excl_group = parser.add_mutually_exclusive_group()
excl_group.add_argument('--split', action='store_true', help="Split package in two zip files")
excl_group.add_argument('--install', action='store_true', help="Install package after build")