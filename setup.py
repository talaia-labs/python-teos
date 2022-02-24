import os
import glob
import shutil
import setuptools

from teos import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()


# Remove undesired files
wildcards = ["**/__pycache__", "**/.DS_Store"]
for entry in wildcards:
    for file_dir in glob.glob(entry, recursive=True):
        if os.path.isdir(file_dir):
            shutil.rmtree(file_dir)
        elif os.path.isfile(file_dir):
            os.remove(file_dir)

# Installing common library only
if os.getenv("COMMON_ONLY", False):
    PACKAGES = ["common"]
    CONSOLE_SCRIPTS = []

    with open("common/requirements.txt") as f:
        requirements = [r for r in f.read().split("\n") if len(r)]
else:
    PACKAGES = ["common", "teos", "teos.cli", "teos.protobuf", "teos.utils"]
    CONSOLE_SCRIPTS = ["teosd=teos.teosd:run", "teos-cli=teos.cli.teos_cli:run"]

    with open("requirements.txt") as f:
        requirements = [r for r in f.read().split("\n") if len(r)]

# Add additional scripts if DEV=1
if os.getenv("DEV", False):
    # Add missing requirements
    with open("contrib/client/requirements.txt") as f:
        requirements_client = [r for r in f.read().split("\n") if len(r)]

    requirements = list(set(requirements).union(requirements_client))

    # Extend packages
    PACKAGES.extend(["contrib", "contrib.client"])

    # Add console scripts
    CONSOLE_SCRIPTS.append("teos-client=contrib.client.teos_client:run")

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
    name="python-teos",
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
    entry_points={"console_scripts": CONSOLE_SCRIPTS},
)
