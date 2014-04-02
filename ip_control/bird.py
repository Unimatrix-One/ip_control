import re
import netaddr
import os.path
from datetime import datetime
import subprocess
import logging
import threading

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
    network = netaddr.IPNetwork(network)

    # Add network route
    RoutingDaemon.instance().add_network(network)

    self._networks.add(network)

  def remove_network(self, network):
    network = netaddr.IPNetwork(network)

    if network not in self._networks:
      return

    # Remove network route
    RoutingDaemon.instance().remove_network(network)

    self._networks.remove(network)

  def has_network(self, network):
    network = netaddr.IPNetwork(network)
    return network in self._networks

  @property
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

class RoutingDaemon(threading.Thread):
  """
  A thread for ensuring presence of IP routes.
  """
  _instance = None

  def __init__(self, *args, **kwargs):
    super(RoutingDaemon, self).__init__(*args, **kwargs)
    self.daemon = True

    self.networks = set([])
    self.pending_networks = set([])

    self._sets_lock = threading.Condition()

  def _cmd(self, cmd, split = True, **kwargs):
    from configuration import config

    cmd = config.get('General', cmd)
    cmd = cmd.format(**kwargs)
    if split:
      cmd = cmd.split(' ')
    return cmd

  def add_network(self, network):
    self._sets_lock.acquire()
    self.pending_networks.add(network)
    self._sets_lock.notify()
    self._sets_lock.release()

  def remove_network(self, network):
    self._sets_lock.acquire()
    if network in self.networks:
      self.networks.remove(network)
      subprocess.call(self._cmd('remove_route', network   = network,
                                                interface = self._get_interface(network)))
    else:
      self.pending_networks.remove(network)
    self._sets_lock.release()

  def _get_interface(self, network):
    from configuration import config
    return config.get(str(network), 'interface')

  def run(self):
    self._sets_lock.acquire()
    while True:
      for network in set(self.pending_networks):
        if not subprocess.call(self._cmd('add_route', network   = network,
                                                      interface = self._get_interface(network))):
          self.pending_networks.remove(network)
          self.networks.add(network)
        elif not subprocess.call(self._cmd('ipv%d_check_route' % network.version,
                                           split     = False,
                                           network   = network.ip if not network.hostmask.value else network,
                                           interface = self._get_interface(network)), shell = True):
          self.pending_networks.remove(network)
          self.networks.add(network)

      # Wait for new
      timeout = None
      if self.pending_networks:
        # Retry in 2 seconds
        timeout = 2
      self._sets_lock.wait(timeout)
    self._sets_lock.release()

  @staticmethod
  def instance():
    if not RoutingDaemon._instance:
      RoutingDaemon._instance = RoutingDaemon()
      RoutingDaemon._instance.start()
    return RoutingDaemon._instance

