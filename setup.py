from setuptools import setup, find_packages

requires = [
    'python-telegram-bot',
    'pyyaml',
    'google-api-python-client',
    'google-auth-httplib2',
    'google-auth-oauthlib',
    'python-redmine'
]

setup(
    name='work assistant',
    version='0.1',
    description='telegram bot for simplifying some work processes',
    classifiers=[
        'Programming Language :: Python',
    ],
    author='atronah',
    author_email='atronah.ds@gmail.com',
    keywords='python telegram bot gmail otrs redmine',
    packages=find_packages(),
    install_requires=requires,
)