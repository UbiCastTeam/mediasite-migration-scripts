#!/usr/bin/python3
# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name='mediaimport',
    version='0.1',
    description='Scripts for migrating media from Mediasite platform',
    author='Nicolas Antunes',
    author_email='nicolas.antunes@ubicast.eu',
    url='https://github.com/UbiCastTeam/mediasite-migration-scripts',
    license='Proprietary',
    packages=find_packages(),
    package_data={'': ['*.json']},
    scripts=[
        'bin/metadata_extract.py',
        'bin/importmedia.py',
        'bin/stats.py'
    ],
    setup_requires=[
        'setuptools >= 3.3',
    ],
    install_requires=[
        'requests'
    ],
    test_suite="tests"
)
