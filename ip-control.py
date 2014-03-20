#!/usr/bin/python
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer, \
                                           SimpleJSONRPCRequestHandler
import argparse
from ip_control import configuration
import os
import os.path
import signal
import logging
import logging.config

parser = argparse.ArgumentParser(description = 'Manages dynamic IP routes for hosted LXCs.')
parser.add_argument('--example-cfg', dest = 'print_config', action = 'store_true',
                    help = 'Prints out an example configuration.')
parser.add_argument('--config', '-c', dest = 'config', type = str, default = '/etc/ip-control.conf',
                    help = 'Specify alternate config file.')
parser.add_argument('--revert', '-r', dest = 'revert_old', action = 'store_true',
                    help = 'Specify alternate config file.')
parser.add_argument('--log-to', '-l', dest = 'logging', nargs = '+', type = str, default = ['console'],
                    help = 'Specify logging output. Possible values are console and syslog')

args = parser.parse_args()

if args.print_config:
  # Create example configuration
  configuration.write_example()
  exit(0)

# Init logging
logging.config.dictConfig({
  'version': 1,
  'formatters': {
    'default': {
      'format': "ip-control - %(levelname)s: %(message)s"
    },
    'console': {
      'format': "%(asctime)s - %(levelname)s: %(message)s"
    }
  },
  'handlers': {
    'syslog': {
      'class': 'logging.handlers.SysLogHandler',
      'formatter': 'default',
      'address': '/dev/log'
    },
    'console': {
      'class': 'logging.StreamHandler',
      'formatter': 'console',
    }
  },
  'root': {
    'handlers': set(args.logging),
    'level': 'INFO'
  }
})

# Load config file
config = configuration.init(args.config)

if not config.has_option('General', 'bind_ip'):
  raise Exception("Bind IP is not specified inside config!")


from ip_control.rpc import RPC
import dns.resolver
import subprocess
import re

# Register signals
def reconfigure(_a, _b):
  global rpc_instance, config
  config = configuration.init(args.config)
  rpc_instance.configure()
signal.signal(signal.SIGHUP, reconfigure)

class RequestHandler(SimpleJSONRPCRequestHandler):
  def __init__(self, request, client_address, server):
    global rpc_instance
    rpc_instance.client_address, _ = client_address

    SimpleJSONRPCRequestHandler.__init__(self, request, client_address, server)

# Get bind information
try:
  # Get FQDN
  hostname = subprocess.check_output(['hostname', '-f']).strip()
  # Resolve it
  logging.info("Resolving %s", hostname)
  bind_ip = dns.resolver.query(hostname)[0].to_text()
except subprocess.CalledProcessError:
  logging.error("Unable to retrieve router's hostname")
  exit(1)
except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
  logging.error("Unable to resolve router's hostname")
  exit(1)
logging.info("Binding to address %s", bind_ip)
try:
  control_domain = config.get('General', 'ip_control_dns_name')
  # Get bind port
  logging.info("Resolving %s TXT record", control_domain)
  bind_port = dns.resolver.query(control_domain, 'TXT')[0].to_text()
  logging.info("Resolved to %s", bind_port)
except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
  logging.error("Unable to resolve %s TXT record to fetch bind port", control_domain)
  exit(1)
bind_port = re.search(r'\s?port=(\d+)', bind_port)
if not bind_port:
  logging.error("Invalid TXT record for %s", control_domain)
  exit(1)
else:
  bind_port = int(bind_port.group(1))
  logging.info("Binding to port %d", bind_port)

# Setup our server
rpc_instance = RPC(args.revert_old, bind_ip, bind_port)
server = SimpleJSONRPCServer((bind_ip, bind_port),
                             requestHandler = RequestHandler)

server.register_instance(rpc_instance)

# Start it up
server.serve_forever()
