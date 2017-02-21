import setuptools

setup_params = dict(
    name='machinerry',
    version='0.1.1',
    author="Allan Crooks",
    author_email="allan.crooks@sixtyten.org",
    url="https://github.com/the-allanc/machinerry",
    py_modules=['machinerry'],
    install_requires=[
        'CherryPy',
    ],
    description='CherryPy-based framework for running tasks repeatedly.',
    long_description=open('README.rst').read(),
)

if __name__ == '__main__':
    setuptools.setup(**setup_params)

