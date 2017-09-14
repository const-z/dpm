
import sys
import logging
from . import install
from . import build
from . import version
from .utils import parser, log

def main():
    args = parser.parse_args()
    if getattr(args, 'verbose', False):
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level = level, format='%(message)s')
    args.func(args)