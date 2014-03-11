from setuptools import setup, find_packages

setup(
  name = "IP Control",
  version = "1.0",
  packages = find_packages(),
  install_requires = ["netaddr",
                      "dnspython",
                      "jsonrpclib"],
  scripts = ["ip-control.py"],

  author = "Unimatriks, d.o.o.",
  author_email = "info@unimatrix.si",
  description = "IP Control.",
  license = "Internal",
  keywords = "bird jsonrpc dns"
)
