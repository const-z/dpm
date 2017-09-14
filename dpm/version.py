from .utils import subparsers, log
from . import __VERSION__

def version(args):
    log.info('.'.join((str(v) for v in __VERSION__)))

parser = subparsers.add_parser('version', help='prints version')
parser.set_defaults(func=version)