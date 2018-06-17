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

Customisation
=============

bumpversion or setuptools_scm
-----------------------------

You'll need to decide whether to use `bumpversion <https://github.com/peritus/bumpversion>`_ or `setuptools_scm <https://github.com/pypa/setuptools_scm>`_ for handling version numbers.

My recommendation is as follows:
  - If you are using an unpredictable versioning scheme, then drop use of `bumpversion`.
  - Otherwise, if you are only ever going to build from tagged commits, then drop `setuptools_scm` instead.
  - You should use **both** if you want `bumpversion` to keep track of your current version, but you also want to build releases from untagged commits - `setuptools_scm` is great for generating an automatic version for you in that situation.

Modification
------------

To integrate skeleton into your project - the minimum changes required are as follows:
  - Remove `README-skeleton.rst` if it exists.
  - Modify the lines at the top of `README.rst` to define the project's name and summary, as well as the links to the project's repository and documentation.
  - Change all references from `SKELETON` in the badges section of `README.rst`.
  - Update `tox.ini` and change the files to look at for `pylint` and coverage when running `py.test` .
  - Add a description for the project (if required) in `README.rst`.
  - Also modify `setup.py` to indicate if the project is a single or multiple module project.
  - Update `docs/index.rst` and choose either the multi-document API approach or the inline API approach, then update the name of the automodule being used in `docs/main.rst`.
  - Either remove the `version` parameter or the `use_scm_version` parameter in `setup.py` depending on whether you're using `setuptools_scm` or `bumpversion` for managing version numbers.
  - If you are not using `setuptools_scm`, then you can remove the dependency on it in `setup.py`.
  - If you are not using `bumpversion`, then you can remove the dependency in `requirements-dev.txt` and its configuration in `setup.cfg`.

If this is done successfully, then there shouldn't be any mentions of the word ``SKELETON`` in any files (apart from `.travis.yml` which will indicate that it should be left).
