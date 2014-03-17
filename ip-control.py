#!/usr/bin/python
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCServer, \
                                           SimpleJSONRPCRequestHandler
import argparse
from ip_control import configuration
import os
import os.path
import signal

parser = argparse.ArgumentParser(description = 'Manages IP allocations for hosted LXCs.')
parser.add_argument('--example-cfg', dest = 'print_config', action = 'store_true',
                    help = 'Prints out an example configuration.')
parser.add_argument('--config', '-c', dest = 'config', type = str, default = '/etc/ip-control.conf',
                    help = 'Specify alternate config file.')
parser.add_argument('--revert', '-r', dest = 'revert_old', action = 'store_true',
                    help = 'Specify alternate config file.')

args = parser.parse_args()

if args.print_config:
  # Create example configuration
  configuration.write_example()
  exit(0)

# Load config file
config = configuration.init(args.config)

if not config.has_option('General', 'bind_ip'):
  raise Exception("Bind IP is not specified inside config!")


from ip_control.rpc import RPC
rpc_instance = RPC(args.revert_old)

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

# Setup our server
server = SimpleJSONRPCServer((config.get('General', 'bind_ip'), config.getint('General', 'bind_port')),
                             requestHandler = RequestHandler)

server.register_instance(rpc_instance)

# Start it up
server.serve_forever()
