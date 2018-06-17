#!/usr/bin/env python
# -*- coding: utf-8 -*-
import io
import os
import sys

# Current preferred theme.
html_theme = 'yeen'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.viewcode',
    'jaraco.packaging.sphinx',
    'rst.linker',
    'conf_as_extension',
]

master_doc = 'index'
autodoc_member_order = 'bysource'
intersphinx_mapping = {'python': ('https://docs.python.org/3', None)}

# Stops module name being prefixed to API documentation.
add_module_names = False

# This allows the conf_as_extension module to be imported.
sys.path.append(os.path.dirname(__file__))

link_files = {
    '../CHANGES.rst': dict(
        using=dict(
            GH='https://github.com',
        ),
        replace=[
            dict(
                pattern=r'(Issue #|\B#)(?P<issue>\d+)',
                url='{package_url}/issues/{issue}',
            ),
            dict(
                pattern=r'^(?m)((?P<scm_version>v?\d+(\.\d+){1,2}))\n[-=]+\n',
                with_scm='{text}\n*{rev[timestamp]:%d %b %Y}*\n',
            ),
            dict(
                pattern=r'PEP[- ](?P<pep_number>\d+)',
                url='https://www.python.org/dev/peps/pep-{pep_number:0>4}/',
            ),
        ],
    ),
}

# Extract the repository URL from the README.
with io.open('../README.rst', encoding='utf-8') as readme:
    repo_prefix = '.. _repository: '
    repo_url = None
    for line in readme.readlines():
        if line.startswith(repo_prefix):
            repo_url = line[len(repo_prefix):].strip()
            break
    del readme, repo_prefix, line

if html_theme == 'yeen' and repo_url.startswith('https://github.com'):
    html_theme_options = {'github_url': repo_url}

with io.open('index.rst', encoding='utf-8') as index_contents:
    # If we're embedding an API file in the main document (presumably
    # just one of them), then exclude individual generation of the API
    # document file, otherwise Sphinx will complain about duplicate
    # object description.
    if '.. include:: api/' in index_contents.read():
        exclude_patterns = ['api/*.rst']
    del index_contents

