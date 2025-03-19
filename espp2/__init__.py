from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("espp2")
except PackageNotFoundError:
    # package is not installed
    pass
