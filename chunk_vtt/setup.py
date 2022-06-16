from importlib.metadata import entry_points
from setuptools import setup, find_packages


setup(
    name="chunk_vtt",
    version="1.0",
    py_modules=["chun_vtt"],
    install_requires=["webvtt-py"],
    entry_points={"console_scripts": ["chunk-vtt=chunk_vtt:main"]},
)
