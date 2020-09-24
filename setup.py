import os
import shutil
import setuptools

from teos import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

with open("requirements.txt") as f:
    requirements = [r for r in f.read().split("\n") if len(r)]


# Remove undesired files
PACKAGES = ["common", "teos", "teos.cli", "teos.protobuf", "teos.utils"]

for package in PACKAGES:
    if os.path.exists(f"{package}/__pycache__"):
        shutil.rmtree(f"{package}/__pycache__")
    if os.path.exists(f"{package}/.DS_Store"):
        os.remove(f"{package}/.DS_Store")

CLASSIFIERS = [
    "Programming Language :: Python",
    "Programming Language :: Python :: 3",
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
    name="teos",
    version=__version__,
    author="Talaia Labs",
    author_email="contact@talaia.watch",
    description="The Eye of Satoshi - Lightning Watchtower",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/talaia-labs/python-teos",
    packages=setuptools.find_packages(include=PACKAGES),
    classifiers=CLASSIFIERS,
    python_requires=">=3.7",
    install_requires=requirements,
    entry_points={"console_scripts": ["teosd=teos.teosd:run", "teos_cli=teos.cli.teos_cli:run"]},
)
