.. SKELETON: This file should be removed from the repository.

About
=====

.. _blog post: https://blog.jaraco.com/a-project-skeleton-for-python-projects/

First of all, I should point out that it's the `hard work of jaraco <https://github.com/jaraco/skeleton>`_ that allows this project to exist. Read his `blog post`_ for an explanation of the project.

My personal fork is spread across two repositories:
 - My `skeleton <https://github.com/the-allanc/skeleton/>`_ project is a fork of the original skeleton project.
 - My `bones <https://github.com/the-allanc/bones/>`_ project is a "digest" version of the skeleton project - it is periodically updated with the content of the skeleton repo, but without the vast history of changesets.

While you are free to import the skeleton project, my recommendation would be to merge in the bones repository as it will add less commit *noise* to your repository.

Integration
===========

Following the advice from the `blog post`_, here's how to keep the skeleton changes in a separate branch:

New repository
--------------

.. code-block::

  $ git init my-project
  $ cd my-project
  $ git pull https://git@github.com/the-allanc/bones/

Existing repository
-------------------

.. code-block::

  $ git checkout --orphan skeleton
  $ git rm -f -r .
  $ git pull https://git@github.com/the-allanc/bones/
  $ git checkout master
  $ git merge skeleton --allow-unrelated-histories # requires Git 2.11 or greater
  
And then to keep it updated, you just need to pull and merge changes in.

Modification
============

When integrating the skeleton into your project - the minimum changes required are as follows:
  - Remove `README-skeleton.rst` if it exists.
  - Modify the lines at the top of `README.rst` to define the project's name and summary, as well as the links to the project's repository and documentation.
  - Change all references from `SKELETON` in the badges section of `README.rst`.
  - Update `.travis.yml` and change the files to look at for coverage when running `py.test`.
  - Add a description for the project (if required) in `README.rst`.
  - Modify the parameters of `setup.py` to remove one of the version parameters defining whether `bumpversion <https://github.com/peritus/bumpversion>`_ or `setuptools_scm <https://github.com/pypa/setuptools_scm>`_ is used for versioning.
  - Also modify setup.py to indicate if the project is a single or multiple module project.
  - Update docs/index.rst and choose either the multi-document API approach or the inline API approach (if the latter, then update the name of the automodule being used).
  - If bumpversion isn't being used, then remove mention of it from requirements-dev.txt and remove the .bumpversion.cfg file.

If this is done successfully, then there shouldn't be any mentions of the word ``SKELETON`` in any files (apart from `.travis.yml` which will indicate that it should be left).
