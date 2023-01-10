from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="espp2",  # Required
    version="0.0.1",  # Required
    description="A tax tool for ESPP/RSU amd foreign held shares",  # Optional
    long_description=long_description,  # Optional
    long_description_content_type="text/markdown",  # Optional (see note above)
    url="https://github.com/pypa/sampleproject",  # Optional
    author="A. Random Developer",  # Optional
    author_email="author@example.com",  # Optional
    packages=find_packages(),  # Required
    python_requires=">=3.9, <4",
    install_requires=["simplejson"],  # Optional
    package_data={  # Optional
        "espp2": ["*.json"],
    },
    entry_points={  # Optional
        "console_scripts": [
            ['espp2=espp2.espp2:main',
            'espp2_transnorm=espp2.transnorm:main'],
        ],
    },
)