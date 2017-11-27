Installing
----------

.. _virtualenv: http://docs.python-guide.org/en/latest/dev/virtualenvs/

You can install |projname| using pip:

.. parsed-literal::

   pip install |projname|

Or you can clone the |projname| repository_, and in an activated virtualenv_, run this command::

    pip install .


Developing
----------

If you want to work on the project, then clone the repository_, and after creating a virtualenv_, and run::

    pip install -r requirements-dev.txt

Testing
~~~~~~~

You can just `tox <https://tox.readthedocs.io/en/latest/>`_ to run the test suite::

    tox

Documentation
~~~~~~~~~~~~~

You can generate documentation using `Sphinx <http://www.sphinx-doc.org>`_::

    sphinx-build docs/ build/docs/

