import os
import shutil
import setuptools

from common import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

with open("common/requirements.txt") as f:
    requirements = [r for r in f.read().split("\n") if len(r)]


# Remove undesired files
if os.path.exists("common/__pycache__"):
    shutil.rmtree("common/__pycache__")
if os.path.exists("common/.DS_Store"):
    os.remove("common/.DS_Store")

CLASSIFIERS = [
    "Programming Language :: Python",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.6",
    "Programming Language :: Python :: 3.7",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3 :: Only",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Topic :: Internet",
    "Topic :: Utilities",
    "Topic :: Software Development :: Libraries :: Python Modules",
]

setuptools.setup(
    name="teos_common",
    version=__version__,
    author="Talaia Labs",
    author_email="contact@talaia.watch",
    description="Common library for The Eye of Satoshi",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/talaia-labs/python-teos",
    packages=setuptools.find_packages(),
    classifiers=CLASSIFIERS,
    python_requires=">=3.6",
    install_requires=requirements,
)
