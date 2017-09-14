
import os
import sys
import re
import yaml
import argparse
import logging
import subprocess
import platform
import time
import io
import json
import shlex
import signal
import builtins
import requests
import progressbar
import rfc6266
import locale
import codecs
from datetime import datetime

__all__ = [
    'run_process',
    'log',
    'parser',
    'subparsers',
    'platform_name',
    'platform_arch',
    'system_name',
    'info_from_name',
    'get_install_path',
    'get_package_yaml',
    'get_package_list',
    'save_package_list',
    'find_python',
    'system',
    'download'
    ]

log = logging.getLogger('dpm')

parser = argparse.ArgumentParser(prog='dpm')
subparsers = parser.add_subparsers(help='command', metavar='command')
subparsers.required = True
    
from threading import Thread
from queue import Queue, Empty
import ctypes

class DownloadError(Exception):
    def __str__(self):
        return 'DownloadError: ' + Exception.__str__(self)

def download(target_dir, url):
    response = requests.get(url, stream=True)

    if not response.ok:
        raise DownloadError('Can\'t download %s: response status: %i'%\
            (url, response.status_code))

    fname = None
    cd = response.headers.get('Content-Disposition')
    if cd:
        fname = rfc6266.parse_headers(cd).filename_unsafe
    if not fname:
        fname = os.path.basename(url)

    log.info('Downloading %s'%fname)

    total = response.headers.get('content-length').strip()
    if total:
        total = int(total)
    path = os.path.join(target_dir, fname)

    with open(path, 'wb') as f:
        widgets = [progressbar.Percentage(), ' ', progressbar.Bar(),
                   ' ', progressbar.ETA(), ' ', progressbar.FileTransferSpeed()]
        pbar = progressbar.ProgressBar(widgets=widgets, max_value=total).start()
        size = 0
        for block in response.iter_content(1024):
            size += len(block)
            f.write(block)
            pbar.update(size)
        pbar.finish()
    return path

def run_process(*args, command=None, stop=None, stdout=log.debug,
        stderr=log.error, cwd=None, format_kwargs=None,
        yield_func=None, **kwargs):
    
    if isinstance(command, dict):
        if 'cwd' in command:
            command_cwd = command['cwd']
            if format_kwargs:
                command_cwd = command_cwd.format(**format_kwargs)
            command_cwd = os.path.expandvars(command_cwd)
            if not os.path.isabs(command_cwd) and cwd:
                cwd = os.path.join(cwd, command_cwd)
            else:
                cwd = command_cwd
        if 'args' in command:
            args = tuple(command['args']) + args

    elif isinstance(command, str):
        args = tuple(shlex.split(command)) + args

    if format_kwargs:
        args = [v.format(**format_kwargs) for v in args]

    log.debug('running: %s'%' '.join([shlex.quote(v) for v in args]))

    current_dir = os.getcwd()
    os.chdir(cwd)
    try:
        proc = subprocess.Popen(args, stdout = subprocess.PIPE,
            stderr = subprocess.PIPE, **kwargs)
    finally:
        os.chdir(current_dir)

    def wait():
        proc.wait()
        q.put(lambda: None)

    def read(stream, out):
        if isinstance(stream, io.TextIOWrapper):
            if callable(out):
                result = ''
                for char in iter(lambda: stream.read(1), ''):
                    if char in ('\n', '\r'):
                        if result:
                            q.put(lambda o=result: out(o))
                            result = ''
                    else:
                        result += char
                if result:
                    q.put(lambda o=result[:-1]: out(o))
            elif isinstance(out, io.StringIO):
                for data in iter(stream.read, b''):
                    out.write(data)
            elif isinstance(out, io.BytesIO):
                for data in iter(stream.read, b''):
                    out.write(data.encode('utf8'))     
        else:
            if callable(out):
                encoding = locale.getpreferredencoding(False)
                result = ''
                it = iter(lambda: stream.read(1), b'')
                for char in codecs.iterdecode(it, encoding, errors='ignore'):
                    if char in ('\n', '\r'):
                        q.put(lambda o=result: out(o))
                        result = ''
                    else:
                        result += char
                if result:
                    q.put(lambda o=result[:-1]: out(o))
            elif isinstance(out, io.StringIO):
                encoding = locale.getpreferredencoding(False)
                it = iter(stream.read, b'')
                for data in codecs.iterdecode(it, encoding, errors='ignore'):
                    out.write(data)
            elif isinstance(out, io.BytesIO):
                for data in iter(stream.read, b''):
                    out.write(data)

    q = Queue()        
    running = True
    exc = None

    threads = [ Thread(target = wait, daemon=True) ]

    if stdout is not None:
        th = Thread(target = read, daemon=True, args=(proc.stdout, stdout))      
        threads.append(th)

    if stderr is not None:
        th = Thread(target = read, daemon=True, args=(proc.stderr, stderr))      
        threads.append(th)

    for v in threads:
        v.start()

    while True:
        try:
            while True:
                if yield_func is not None:
                    yield_func()
                if running and stop is not None and stop():
                    log.debug('process terminated!')
                    try:
                        os.kill(proc.pid, signal.SIGTERM)
                    except:
                        pass
                    running = False
                alive = any((v.is_alive() for v in threads))
                try:
                    q.get(alive, timeout=0.1)()
                except Empty:
                    if not alive:
                        break
            break
        except KeyboardInterrupt as e:
            if running:
                log.debug('process interrupted!')
                try:
                    os.kill(proc.pid, signal.SIGINT)
                except:
                    pass
                running = False
                exc = e

    if exc:
        raise exc
    else:
        log.debug('return code: %i'%proc.returncode)
        return proc.returncode == 0

is_64bits = sys.maxsize > 2**32
system = platform.system()

if is_64bits:
    platform_arch = '64'
else:
    platform_arch = '32'

if system == 'Windows':
    system_name = 'win'
    platform_name = 'win'+platform_arch
    py_search_paths = [
            ['python.exe'],
            ['Scripts', 'python.exe'],
        ]
elif system == 'Linux':
    system_name = 'linux'
    platform_name = 'linux'+platform_arch
    py_search_paths = [
            ['bin', 'python'],
        ]
else:
    system_name = 'unknown'
    platform_name = 'unknown'+platform_arch

def find_python(python_path, base_path=''):
    python_path = os.path.expandvars(python_path)
    base_path = os.path.expandvars(base_path)
    if not os.path.isabs(python_path):
        python_path = os.path.join(base_path, python_path)
    if os.path.isdir(python_path):
        for v in py_search_paths:
            result = os.path.join(python_path, *v)
            if os.path.exists(result):
                return os.path.normpath(result)
    else:
        return os.path.normpath(python_path)

packages_install_dir  = os.path.join(os.path.expanduser("~"), ".DICE", "data", "packages")
dice_config = os.path.join(os.path.expanduser("~"), ".DICE", "config", "dice.json")

def get_install_path(package_name):
    package_name = package_name.replace('/', '-')
    default_dir = packages_install_dir
    paths = []
    if os.path.exists(dice_config):
        with open(dice_config) as f:
            cfg = json.load(f)
            paths += cfg.get('packages_dirs', [])
            if 'packages_install_dir' in cfg:
                default_dir = cfg['packages_install_dir']
    paths.append(default_dir)
    for v in set(paths):
        package_dir = os.path.join(v, package_name)
        if os.path.exists(package_dir):
            return package_dir
    return os.path.join(default_dir, package_name)

def get_package_yaml(package_name, file_name):
    package_yaml = os.path.join(get_install_path(package_name), file_name)
    if os.path.exists(package_yaml):
        with open(package_yaml, 'r') as f:
            return yaml.load(f)

def get_package_list(package_name, file_name):
    path = os.path.join(get_install_path(package_name), file_name)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return f.read().split('\n')
    return []

def save_package_list(package_name, file_name, items):
    install_path = get_install_path(package_name)
    path = os.path.join(install_path, file_name)
    with open(path, 'w') as f:
        f.write('\n'.join(items))

def info_from_name(package):
    values = package.split('==')
    name, values = values[0], values[1:]
    version, values = (values[0], values[1:]) if values else ('latest', values)
    machine, values = (values[0], values[1:]) if values else (platform_name, values)
    return name, version, machine

