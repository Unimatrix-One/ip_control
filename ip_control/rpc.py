import logging
import logging.handlers
import dns.resolver
import dns.reversename
import netaddr
import jsonrpclib
from ip_control.configuration import config
from ip_control.bird import BirdConfig

logger = logging.getLogger('ip-control.rpc')
logger.addHandler(logging.handlers.SysLogHandler(address = '/dev/log'))

class RPC(object):
  def __init__(self):
    self._controllers = set([])
    if config.has_option('General', 'ip_control_dns_name'):
      self_ip = netaddr.IPNetwork(config.get('General', 'bind_ip'))
      for answer in dns.resolver.query(config.get('General', 'ip_control_dns_name'), 'A'):
        ip = netaddr.IPNetwork(str(answer))
        if ip == self_ip:
          # Ignore itself
          continue
        self._controllers.add(jsonrpclib.Server("http://{}:{}/".format(ip, config.get('General', 'bind_port'))))
    # Initialize Birds
    self._bird = {
      4: BirdConfig(4),
      6: BirdConfig(6)
    }

    self._networks = {}
    for section in (i for i in config.sections if i != 'General'):
      network = netaddr.IPNetwork(section)
      # Get allowed hosts, also check them if are properly configured
      allowed_hosts = [i.strip() for i in config.get(section, 'allowed_hosts').split(',')]
      allowed_hosts = set([i if i.endswith('.') else i + '.' for i in allowed_hosts])
      for host in allowed_hosts:
        try:
          address = dns.resolver.query(host)
          if len(address) > 1:
            logger.error("Host {} resolves to multiple IP addresses, removing from allowed hosts.".format(host))
            allowed_hosts.remove(host)
            continue
          address = address[0]
        except dns.resolver.NoAnswer:
          logger.error("Host {} has no DNS record, removing it from allowed hosts.". format(host))
          allowed_hosts.remove(host)
          continue
        # Check reverse lookup
        try:
          reverse_lookup = dns.resolver.query(dns.reversename.from_address(address), 'PTR')
          if len(reverse_lookup) > 1:
            logger.error("Host's {} IP {} has many reverse records, removing it from allowed hosts.".format(host, address))
            allowed_hosts.remove(host)
            continue
          reverse_lookup = reverse_lookup[0]
        except dns.resolver.NoAnswer:
          logger.error("Host's {} IP {} has no reverse DNS record, removing it from allowed hosts.".format(host, address))
          allowed_hosts.remove(host)
          continue
        # Does host and reversed looked up host match?
        if host != reverse_lookup:
          logger.error("Host {} and it's reverse {} from IP {} does not match, removing it from allowed hosts.".format(host, reverse_lookup, address))
          allowed_hosts.remove(host)

      # Add network
      self._networks[network] = {
        'allowed_hosts': allowed_hosts,
        'unique': not network.hostmask.value or (not config.getboolean(section, 'unicast') if config.has_option(section, 'unicast') else True)
      }

  def enable(network):
    network = netaddr.IPNetwork(network)
    network_config = self._check_access(network)

    if network_config.get('unique', True):
      # Disable this IP over all controllers
      for controller in self._controllers:
        try:
          controller.disable(str(network))
        except:
          # Ignore exception, just log it
          logger.exception("There was an exception when trying to disable the network {} on controller {}:".format(network, controller))

    if not self._bird[network.version].has_network(network):
      self._bird[network.version].remove(network)
      self._bird[network.version].save()

  def disable(network):
    network = netaddr.IPNetwork(network)
    self._check_access(network)

    if self._bird[network.version].has_network(network):
      self._bird[network.version].remove(network)
      self._bird[network.version].save()

  def _check_access(network):
    network_config = self._networks.get(network, None)
    if not network_config:
      raise Exception("Network {} not known at this controller.".format(network))

    # Resolve IP into host name
    try:
      client = dns.resolver.query(dns.reversename.from_address(self.client_address), 'PTR')
    except dns.resolver.NoAnswer:
      logger.error("IP {} has no reverse records.".format(self.client_address))
      raise Exception("Access denied")
    # Check if we have host on the list of allowed hosts
    if client not in network_config.get('allowed_hosts', set([])):
      logger.warning("Client from {} tried to change network {} OSPF advertisment.".format(client, network))
      raise Exception("Access denied")

    return network_config

  def status(network):
    network = netaddr.IPNetwork(ip)
    return 'enabled' if self._bird[network.version].has_network(network) else 'disabled'
