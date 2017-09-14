from setuptools import setup, find_packages
from dpm import __VERSION__
import os

with open('README.md') as f:
    long_description = f.read()

setup(
    name='dpm',
    version='.'.join((str(v) for v in __VERSION__)),
    author='DICEhub',
    author_email='info@dicehub.com',
    description='DICE package manager',
    long_description=long_description,
    url='http://dicehub.com',
    packages = find_packages(),
    dependency_links=[
        'https://github.com/g2p/rfc6266/archive/master.zip#egg=rfc6266-0.0.4',
    ],
    install_requires=[
        'PyYAML',
        'rfc3987',
        'progressbar2',
        'requests',
        'rfc6266'],
)
