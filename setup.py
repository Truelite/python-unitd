#!/usr/bin/env/python3
from distutils.core import setup
import sys

setup(
    name = "unitd",
    version = "0.1",
    description = "python process management",
    author = ["Enrico Zini"],
    author_email = ["enrico@truelite.it"],
    url = "https://labs.truelite.it/projects/unitd",
    license = "http://www.gnu.org/licenses/agpl-3.0.html",
    packages = ["unitd"],
    scripts=["webrun"],
)
