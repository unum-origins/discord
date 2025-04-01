#!/usr/bin/env python

import os
from setuptools import setup

version = os.environ.get("BUILD_VERSION")

if version is None:
    with open("VERSION", "r") as version_file:
        version = version_file.read().strip()

setup(
    name="unum-origins-discord",
    version=version,
    package_dir = {'': 'daemon/lib'},
    py_modules = ['unum.origins.discord'],
    install_requires=[
        'unum-apps-ledger@git+https://github.com/unum-apps/ledger@0.1.2'
    ]
)
