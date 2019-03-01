import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='dj4xol',
    version='0.1',
    packages=find_packages(exclude=("testsite","manage.py","build-aux")),
    include_package_data=True,
    license='GNU GPL v2',  # example license
    description='A 4x strategy game inspired by Stars!',
    long_description=README,
    url='https://www.bradleygray.co.uk/4x',
    author='Bradley Gray',
    author_email='bradley.gray+pypi@bradleygray.co.uk',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 1.11',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
