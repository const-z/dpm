from .utils import *
import os
import shutil
import logging
import sys

class UninstallError(Exception):
    def __str__(self):
        return 'UninstallError: ' + Exception.__str__(self)

def uninstall(args):
    try:
        packages = args.package
        del args.package
        for package in packages:
            log.info('Uninstalling %s'%package)
            uninstall_package(package, **vars(args))
        log.info('Success')
    except UninstallError as e:
        log.error(str(e))
        sys.exit(1)
    finally:
        pass

parser = subparsers.add_parser('uninstall', help='uninstall package(s)')
parser.set_defaults(func=uninstall)
parser.add_argument('package', nargs='+')
parser.add_argument('-v', '--verbose', action='store_true', help="detailed output")

def uninstall_package(package, dice = None, other_deps = None, **kwargs):
    install_path = get_install_path(package)
    package_info = get_package_yaml(package, 'package.yaml')

    if package_info == None:
        raise UninstallError('Package %s not installed'%package)

    install_info = get_package_yaml(package, 'install.yaml')

    for v in install_info.get('pre_uninstall_cmd', ()):
        if not run_process(command=v, cwd=install_path):
            raise UninstallError('Pre-uninstall command error.')

    try:
        log.debug('deleting: %s', install_path) 
        shutil.rmtree(install_path)
    except Exception as e:
        log.warn('Can\'t delete %s:\n%s', v, str(e))
        log.warn('Not all resources was deleted, verify log above.')

    deps = install_info.get('dependencies')
    if deps:
        if other_deps:
            other_deps = [info_from_name(v)[0] for v in other_deps]
        for v in deps:
            name = info_from_name(v)[0]
            deps_list = get_package_list(name, 'deps.txt')
            if package_info['name'] in deps_list:
                deps_list.remove(package_info['name'])
                save_package_list(name, 'deps.txt', deps_list)
                if (not deps_list and
                        (not other_deps or name not in other_deps)):
                    if input('Package "%s" no longer required\n'
                            'Uninstall? [y/N]:'%dep_info['name']
                            ).lower().startswith('y'):
                        uninstall_package(name)
