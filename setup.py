#!/usr/bin/env python3
""" Bedwetter setup.py. """

from setuptools import setup

setup(
    entry_points="""
        [console_scripts]
        bedwetter=bedwetter.__main__:main
    """,
    include_package_data=True,
    install_requires=[
        "automationhat ; platform_system=='Linux'",
        "crontab",
        "configparser",
        "paho-mqtt",
        "requests",
        "smbus ; platform_system=='Linux'",
    ],
    extras_require={"dev": ["mock"]},
    name="bedwetter",
    packages=["bedwetter"],
    package_data={"": ["ssl/letsencrypt-root.pem"]},
    version="2.0.0",
)
