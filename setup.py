#!/usr/bin/env python

import os
from setuptools import setup

version = os.environ.get("BUILD_VERSION")

if version is None:
    with open("VERSION", "r") as version_file:
        version = version_file.read().strip()

setup(
    name="unum-discord",
    version=version,
    package_dir = {'': 'daemon/lib'},
    py_modules = ['unum_discord'],
    install_requires=[
        'discord.py==2.4.0'
    ]
)

