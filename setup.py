#!/usr/bin/env python3
""" Bedwetter setup.py. """

from setuptools import setup

setup(
    entry_points="""
        [console_scripts]
        bedwetter=bedwetter.__main__:main
    """,
    extras_require={"dev": ["mock"]},
    include_package_data=True,
    install_requires=[
        "automationhat ; platform_system=='Linux'",
        "crontab",
        "configparser",
        "paho-mqtt",
        "python-dateutil",
        "requests",
        "smbus ; platform_system=='Linux'",
    ],
    name="bedwetter",
    packages=["bedwetter"],
    package_data={"": ["ssl/letsencrypt-root.pem"]},
    version="2.0.0",
)
