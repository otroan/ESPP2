import pathlib
from setuptools import setup, find_packages

here = pathlib.Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="espp2",
    version="0.0.2",
    description="A tax tool for ESPP/RSU and foreignly held shares",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/otroan/ESPP2",
    author="O. Troan",
    author_email="otroan@employees.org",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=["simplejson", "numpy", "pydantic",
                      "urllib3", "python-dateutil", "uvicorn", "fastapi",
                      "python-multipart", "tabulate", "pandas", "lxml", "pytest", "httpx",
                      "rich", "typing", "html5lib"],
    package_data={
        "espp2": ["*.json"],
    },
    entry_points={
        "console_scripts": [
            ['espp2=espp2.espp2:app',
            'espp2_transactions=espp2.transactions:main']
        ],
    },
)
