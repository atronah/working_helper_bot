from setuptools import setup, find_packages

requires = [
    'python-telegram-bot',
    'pyyaml',
    'google-api-python-client',
    'google-auth-httplib2',
    'google-auth-oauthlib',
    'python-redmine',
    'python-otrs'
]

setup(
    name='work_assistant',
    version='0.1',
    description='telegram bot for simplifying some work processes',
    classifiers=[
        'Programming Language :: Python',
    ],
    author='atronah',
    author_email='atronah.ds@gmail.com',
    keywords='python telegram bot gmail otrs redmine',
    # using a package folder with the different name than the package
    # for academic purposes (as example)
    package_dir={'work_assistant': 'src'},
    # manual specifying package which is in folder with different name
    packages=['work_assistant'],
    install_requires=requires,
)