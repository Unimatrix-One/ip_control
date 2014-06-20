import re
import netaddr
import os.path
from datetime import datetime
import subprocess
import logging
import threading

class BirdConfig(object):
  _network_re = re.compile(r'^\s*stubnet\s+([^;]+);\s*$')

  def __init__(self, version):
    from ip_control.configuration import config
    self._networks = set([])
    self.version = 6 if str(version) == '6' else 4
    self._filepath = config.get('General', 'bird{}_dynamic_config'.format(self.version))
    self._filepath_routes = config.get('General', 'bird{}_dynamic_routes'.format(self.version))
    self._prepare_path()

    # Prepare commands
    self._reload = config.get('General', 'bird{}_reload'.format(self.version))

    # Load all networks
    self._interfaces = {}
    for network in (i for i in config.sections() if i != 'General'):
      self._interfaces[netaddr.IPNetwork(network)] = config.get(network, 'interface')

    # Load configs
    if os.path.exists(self._filepath):
      self._load()

  def _cmd(self, cmd, **kwargs):
    return getattr(self, '_' + cmd).format(**kwargs).split(' ')

  def _prepare_path(self):
    path = '/'.join(self._filepath.split('/')[:-1])
    if not os.path.exists(path):
      # Create path
      os.makedirs(path)

  def _get_interface(self, network):
    return self._interfaces.get(network, 'lo')

  def _load(self):
    logging.info('Loading existing routes for IPv%d from BIRD configs', self.version)
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

    self._networks.add(network)

  def remove_network(self, network):
    network = netaddr.IPNetwork(network)

    if network not in self._networks:
      return

    self._networks.remove(network)

  def has_network(self, network):
    network = netaddr.IPNetwork(network)
    return network in self._networks

  @property
  def networks(self):
    return set(self._networks)

  def save(self):
    # Make up list of routes
    announcements = []
    for network in self._networks:
      announcements.append('stubnet {};'.format(network))
    routes = []
    for network in self._networks:
      routes.append('route {} via "{}";'.format(network, self._get_interface(network)))

    # Create/rewrite config files
    logging.info('Writing routes for IPv%d to BIRD configs', self.version)
    try:
      output_ann = open(self._filepath, 'w')
      output_ann.write("# Generated by ip-control at {}. Do not touch this file!\n".format(str(datetime.now())))
      output_ann.write("\n".join(announcements))
      output_ann.close()
    except:
      logging.exception('Cannot open %s for writing.', self._filepath)
    try:
      output_routes = open(self._filepath_routes, 'w')
      output_routes.write("# Generated by ip-control at {}. Do not touch this file!\n".format(str(datetime.now())))
      output_routes.write("\n".join(routes))
      output_routes.close()
    except:
      logging.exception('Cannot open %s for writing.', self._filepath)
    # Reload our bird
    try:
      subprocess.check_call(self._cmd('reload'))
    except:
      logging.exception('Got exception when reloading bird%d', self.version)

class HealthCheckDaemon(threading.Thread):
  def __init__(self, bird_daemon, *args, **kwargs):
    super(HealthCheckDaemon, self).__init__(*args, **kwargs)

    self._bird_daemon = bird_daemon
    self._networks = {}
    self._lock = threading.Condition()
    self._running = True

  def add_network(self, network, cmd):
    self._lock.acquire()
    self._networks[network] = cmd
    self._lock.notify()
    self._lock.release()

  def stop(self):
    self._lock.acquire()
    self._running = False
    self._lock.notify()
    self._lock.release()

  def run(self):
    self._lock.acquire()
    while self._running:
      change = False
      # Check networks
      for network, hc in self._networks.items():
        if not subprocess.call(hc, shell = True):
          if not self._bird_daemon.has_network(network):
            logging.info("Health check for network %s has succeeded, enabling it.", network)
            self._bird_daemon.add_network(network)
            change = True
        else:
          if self._bird_daemon.has_network(network):
            logging.warning("Health check for network %s has failed, disabling it.", network)
            self._bird_daemon.remove_network(network)
            change = True

      # Save the configuration
      if change:
        self._bird_daemon.save()

      # Let's wait for next loop
      self._lock.wait(5)
    self._lock.release()
