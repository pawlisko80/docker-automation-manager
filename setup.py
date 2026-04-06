from setuptools import setup, find_packages

setup(
    name="docker-automation-manager",
    version="0.1.0",
    description="Automated Docker container lifecycle manager with platform detection (QNAP, Synology, Generic Linux)",
    author="Pawel",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "docker>=7.0.0",
        "rich>=13.0.0",
        "prompt_toolkit>=3.0.0",
        "pyyaml>=6.0",
        "click>=8.0.0",
        "schedule>=1.2.0",
    ],
    entry_points={
        "console_scripts": [
            "dam=dam.main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
    ],
)
