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

def get_bind_info():
  # Get bind information
  try:
    # Get FQDN
    hostname = subprocess.check_output(['hostname', '-f']).strip()
    # Resolve it
    logging.info("Resolving %s.", hostname)
    bind_ip = dns.resolver.query(hostname)[0].to_text()
  except subprocess.CalledProcessError:
    logging.error("Unable to retrieve router's hostname.")
    return None
  except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
    logging.error("Unable to resolve router's hostname.")
    return None
  logging.info("Binding to address %s.", bind_ip)
  try:
    control_domain = config.get('General', 'ip_control_dns_name')
    # Get bind port
    logging.info("Resolving %s TXT record.", control_domain)
    bind_port = dns.resolver.query(control_domain, 'TXT')[0].to_text()
    logging.info("Resolved to %s.", bind_port)
  except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
    logging.error("Unable to resolve %s TXT record to fetch bind port.", control_domain)
    return None
  bind_port = re.search(r'\s?port=(\d+)', bind_port)
  if not bind_port:
    logging.error("Invalid TXT record for %s.", control_domain)
    return None
  else:
    bind_port = int(bind_port.group(1))
    logging.info("Binding to port %d.", bind_port)

  return (bind_ip, bind_port)

# First, init dynamic routes
# Check for persistance (bootup or daemon restart)
persistance_file = config.get('General', 'persistance_file')
if not os.path.exists(persistance_file):
  # Touch this file
  try:
    open(persistance_file, 'w')
  except IOError:
    logging.error("Cannot create persistance file.")
  # Recreate dynamic files
  open(config.get('General', 'bird4_dynamic_config'), 'w')
  open(config.get('General', 'bird6_dynamic_config'), 'w')

# Setup our server
bind_info = None
while not bind_info:
  try:
    bind_info = get_bind_info()
  except dns.resolver.Timeout:
    logging.warning("Timeout occured when retrieving settings from DNS.")
  except:
    logging.warning("Unknown error occured when retrieving settings from DNS.")
  if not bind_info:
    import time
    time.sleep(5)
rpc_instance = RPC(bind_info)
server = SimpleJSONRPCServer((rpc_instance.bind_ip, rpc_instance.bind_port),
                             requestHandler = RequestHandler)

server.register_instance(rpc_instance)

# Start it up
logging.info("Listening for requests.")
import select
while True:
  try:
    server.serve_forever()
  except select.error:
    # Just go along
    pass
