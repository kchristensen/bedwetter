#!/usr/bin/env python3
""" Bedwetter setup.py. """

from setuptools import setup

setup(
    entry_points='''
        [console_scripts]
        bedwetter=bedwetter.__main__:main
    ''',
    include_package_data=True,
    install_requires=[
        'automationhat ; platform_system=="Linux"',
        'configparser',
        'requests',
        'smbus ; platform_system=="Linux"'
    ],
    name='bedwetter',
    packages=['bedwetter'],
    version='1.0.0'
)
