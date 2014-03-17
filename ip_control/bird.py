import re
import netaddr
import os.path
from datetime import datetime
import subprocess
import logging

class BirdConfig(object):
  _network_re = re.compile(r'^\s*stubnet\s+([^;]+);\s*$')

  def __init__(self, version, revert_old):
    from ip_control.configuration import config
    self._networks = set([])
    self.version = 6 if str(version) == '6' else 4
    self._filepath = config.get('General', 'bird{}_dynamic_config'.format(self.version))
    self._prepare_path()

    # Prepare commands
    self._reload = config.get('General', 'bird{}_reload'.format(self.version))
    self._add_route = config.get('General', 'add_route')
    self._remove_route = config.get('General', 'remove_route')

    # Load configs
    if revert_old or not os.path.exists(self._filepath):
      self.save()
    else:
      self._load()

  def _cmd(self, cmd, **kwargs):
    return getattr(self, '_' + cmd).format(**kwargs).split(' ')

  def _prepare_path(self):
    path = '/'.join(self._filepath.split('/')[:-1])
    if not os.path.exists(path):
      # Create path
      os.makedirs(path)

  def _load(self):
    try:
      c = open(self._filepath, 'r')
    except:
      logging.exception('Cannot open %s for reading.', self._filepath)
      raise

    for line in c:
      match = self._network_re.match(line)
      if match:
        logging.info('Loaded network %s', match.group(1))
        self.add_network(match.group(1))

  def add_network(self, network):
    try:
      # Add network route
      subprocess.check_call(self._cmd('add_route', network = network))
    except:
      logging.exception("Cannot add network %s!", network)

    self._networks.add(netaddr.IPNetwork(network))

  def remove_network(self, network):
    try:
      # Add network route
      subprocess.check_call(self._cmd('remove_route', network = network))
    except:
      logging.exception("Cannot remove network %s!", network)

    network = netaddr.IPNetwork(network)
    if network in self._networks:
      self._networks.remove(network)

  def has_network(self, network):
    network = netaddr.IPNetwork(network)
    return network in self._networks

  def networks(self):
    return set(self._networks)

  def save(self):
    # Create/rewrite config file
    try:
      c = open(self._filepath, 'w')
    except:
      logging.exception('Cannot open %s for writing.', self._filepath)
      raise
    c.write("# Generated by ip-control at {}. Do not touch this file!\n".format(str(datetime.now())))
    # Put our IPs into the file
    for network in self._networks:
      c.write("stubnet {};\n".format(network))
    c.close()
    # Reload our bird
    try:
      subprocess.check_call(self._cmd('reload'))
    except:
      logging.exception('Got exception when reloading bird%d', self.version)
      raise
