#!/usr/bin/env python

# Project skeleton maintained at https://github.com/the-allanc/skeleton
# All the hard work done by jaraco at https://github.com/jaraco/skeleton

#
# Extract the project identity from the README.
#
import io
import setuptools

with io.open('README.rst', encoding='utf-8') as readme:
    readme = readme.read()


def get_definition(prefix):
    for line in readme.split('\n'):
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    err = 'no line in README.rst with prefix {!r}'.format(prefix)
    raise AssertionError(err)


def get_description():
    d_start = '|summary|\n'
    i_start = readme.index(d_start) + len(d_start)
    return readme[i_start:].strip()


name = get_definition('.. |name| replace:: ')
url = get_definition('.. _repository: ')
summary = get_definition('.. |summary| replace:: ')
description = get_description()

#
# End extraction code.
#

params = dict(
    name=name,
    version='0.1',  # SKELETON: Remove if not using bumpversion.
    use_scm_version=True,  # SKELETON: Remove if not using setuptools_scm.
    author="Allan Crooks",
    author_email="allan@increment.one",
    description=summary or name,
    long_description=description,
    license='MIT',
    url=url,
    keywords=[],
    py_modules=['SKELETON'],  # SKELETON: Remove if multiple module project.
    packages=setuptools.find_packages(exclude=['tests']),  # SKELETON: Remove if single module.
    include_package_data=True,
    namespace_packages=name.split('.')[:-1],
    python_requires='>=2.7',
    install_requires=[
        'requests',
        'six',
    ],
    extras_require={
        'testing': [
            'pytest>=2.8',
            'pytest-sugar',
        ],
        'docs': [
            'sphinx',
            'jaraco.packaging>=3.2',
            'rst.linker>=1.9',
            'allanc-sphinx[yeen]>=0.2',
            'collective.checkdocs',
        ],
    },
    setup_requires=[
        'setuptools_scm>=1.15.0',  # SKELETON: Remove if not using setuptools_scm.
    ],
    classifiers=[
        # "Development Status :: 3 - Alpha",
        "Development Status :: 4 - Beta",
        # "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
    entry_points={
    },
)

if __name__ == '__main__':
    setuptools.setup(**params)
