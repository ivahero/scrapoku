#!/usr/bin/env python
import os
import re
from setuptools import setup, find_packages

curdir = os.path.dirname(__file__)

with open(os.path.join(curdir, 'vanko', '__init__.py')) as f:
    VERSION = re.findall(r'__version__\s*=\s*\'(.*)\'', f.read())[0]

with open(os.path.join(curdir, 'README.rst')) as f:
    README = f.read()

setup(
    name='hero-crawl',
    version=VERSION,
    author='Ivan Andreev',
    author_email='ivandeex@gmail.com',
    url='https://github.com/ivandeex/hero-crawl',
    description='Helpers for Scrapy and Flask on Heroku',
    long_description=README,
    license='MIT',
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Framework :: Scrapy',
        'Topic :: Utilities',
        'License :: OSI Approved :: BSD License',
    ],
)
