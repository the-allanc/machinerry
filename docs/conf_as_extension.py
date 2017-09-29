from __future__ import unicode_literals


def setup(app):
    app.connect('builder-inited', init)


prolog = '''
.. |projname| replace:: {0.project}
.. _repository: {0.package_url}
'''


def init(app):
    # I prefer the copyright to include the date.
    if app.config.author == app.config.copyright:
        from datetime import date
        copyright = '{} {}'.format(date.today().year, app.config.author)
        app.config.copyright = copyright
    app.config.rst_epilog = prolog.format(app.config)

    # Version fixing tip from https://github.com/pypa/setuptools_scm
    from pkg_resources import get_distribution
    app.config.version = app.config.release = get_distribution(app.config.project).version
