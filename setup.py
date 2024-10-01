# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name='douyinliverecorder',
    version='3.0.8',
    author='Hmily',
    description='An easy tool for recording live streams',
    long_description=open('README.md', encoding='utf-8').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/ihmily/DouyinLiveRecorder',
    packages=find_packages(),
    install_requires=[
        'requests',
        'PyExecJS',
        'loguru',
        'pycryptodome'
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ]
)
