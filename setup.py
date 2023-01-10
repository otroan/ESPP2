from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="espp2",
    version="0.0.1",
    description="A tax tool for ESPP/RSU amd foreign held shares",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/otroan/ESPP2",
    author="O. Troan",
    author_email="otroan@employees.org",
    packages=find_packages(),
    python_requires=">=3.9, <4",
    install_requires=["simplejson", "numpy"],
    package_data={
        "espp2": ["*.json"],
    },
    entry_points={
        "console_scripts": [
            ['espp2=espp2.espp2:main',
            'espp2_transnorm=espp2.transnorm:main',
            'espp2_genholdings=espp2.genholdings:main'],
        ],
    },
)