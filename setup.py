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
    name='vanko-tools',
    version=VERSION,
    author='Ivan Andreev',
    author_email='ivandeex@gmail.com',
    url='https://github.com/ivandeex/',
    description='Scrapy wrappers and extensions',
    long_description=README,
    license='BSD',
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Scrapy',
        'Topic :: Utilities',
        'License :: OSI Approved :: BSD License',
    ],
)
