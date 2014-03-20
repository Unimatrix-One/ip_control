import logging
import logging.config
import dns.resolver
import dns.reversename
import netaddr
import jsonrpclib
from ip_control.bird import BirdConfig

class RPC(object):
  def __init__(self, revert_old, (bind_ip, bind_port)):
    # Initialize Birds
    self._bird = {
      4: BirdConfig(4, revert_old),
      6: BirdConfig(6, revert_old)
    }
    self.bind_ip = bind_ip
    self.bind_port = bind_port

    self.configure()

  @property
  def _controllers(self):
    controllers = []
    control_domain = config.has_option('General', 'ip_control_dns_name')
    if control_domain:
      self_ip = netaddr.IPNetwork(self.bind_ip)
      for answer in dns.resolver.query(control_domain, 'A'):
        ip = netaddr.IPNetwork(str(answer))
        if ip == self_ip:
          # Ignore itself
          continue
        ip = ip.ip
        try:
          controllers.append(jsonrpclib.Server("http://{}:{}/".format(ip, self.bind_port)))
        except:
          logging.warning("Could not connect to controller %s.", ip)
    return controllers

  def configure(self):
    from ip_control.configuration import config
    logging.info("Configuring")

    self._networks = {}
    for section in (i for i in config.sections() if i != 'General'):
      network = netaddr.IPNetwork(section)
      logging.info('Loading network %s.', network)
      # Check for interface
      if not config.has_option(section, 'interface'):
        logging.warning("Network %s has no interface specified, ignoring it.", network)
        continue
      interface = config.get(section, 'interface')
      # Check if interface exists
      try:
        subprocess.check_call(['/sbin/ifconfig', interface])
      except subprocess.CalledProcessError:
        logging.warning("Interface %s does not exists, ignoring network %s.", interface, network)
        continue
      # Get allowed hosts, also check them if are properly configured
      allowed_hosts = [i.strip() for i in config.get(section, 'allowed_hosts').split(',')]
      allowed_hosts = set([i if i.endswith('.') else i + '.' for i in allowed_hosts])
      for host in [i for i in allowed_hosts]:
        try:
          address = dns.resolver.query(host)
          if len(address) > 1:
            logging.warning("Host %s resolves to multiple IP addresses, removing from allowed hosts.", host)
            allowed_hosts.remove(host)
            continue
          address = address[0]
          logging.info("Host %s resolved to %s", host, address)
        except dns.resolver.NoAnswer:
          logging.warning("Host %s has no DNS record, removing it from allowed hosts.", host)
          allowed_hosts.remove(host)
          continue
        # Check reverse lookup
        try:
          reverse_lookup = dns.resolver.query(dns.reversename.from_address(address.to_text()), 'PTR')
          if len(reverse_lookup) > 1:
            logging.warning("Host's %s IP %s has many reverse records, removing it from allowed hosts.", host, address)
            allowed_hosts.remove(host)
            continue
          reverse_lookup = reverse_lookup[0].to_text()
          logging.info("Resolved IP %s has an inverse record to %s", address, reverse_lookup)
        except dns.resolver.NoAnswer:
          logging.warning("Host's %s IP %s has no reverse DNS record, removing it from allowed hosts.", host, address)
          allowed_hosts.remove(host)
          continue
        # Does host and reversed looked up host match?
        if host != reverse_lookup:
          logging.warning("Host %s and it's reverse %s from IP %s does not match, removing it from allowed hosts.", host, reverse_lookup, address)
          allowed_hosts.remove(host)
        else:
          logging.info("Host's %s DNS records are properly configured.", host)

      # Add network
      self._networks[network] = {
        'allowed_hosts': allowed_hosts,
        'interface': interface,
        'unique': not network.hostmask.value or (not config.getboolean(section, 'unicast') if config.has_option(section, 'unicast') else True)
      }

    # Remove non managed networks (they should not be announced anymore!)
    changed = set([])
    for bird, obsolete_network in ((b, i) for b in self._bird.values() for i in b.networks if i not in self._networks):
      logging.info('Removing obsolete network %s.', obsolete_network)
      bird.remove_network(obsolete_network)
      changed.add(bird)
    for bird in changed:
      bird.save()

  def enable(self, network):
    network = netaddr.IPNetwork(network)
    network_config = self._check_access(network)

    if network_config.get('unique', True):
      # Disable this IP over all controllers
      for controller in self._controllers:
        try:
          if controller.status(str(network)) == 'enabled':
            controller.disable(str(network))
        except:
          # Ignore exception, just log it
          logging.exception("There was an exception when trying to disable the network %s on controller %s:", network, controller)

    if not self._bird[network.version].has_network(network):
      self._bird[network.version].add_network(network, network_config['interface'])
      self._bird[network.version].save()

  def disable(self, network):
    network = netaddr.IPNetwork(network)
    self._check_access(network)

    if self._bird[network.version].has_network(network):
      self._bird[network.version].remove_network(network)
      self._bird[network.version].save()

  def _check_access(self, network):
    network_config = self._networks.get(network, None)
    if not network_config:
      raise Exception("Network {} not known at this controller.".format(network))

    # Resolve IP into host name
    try:
      client = dns.resolver.query(dns.reversename.from_address(self.client_address), 'PTR')
      client = client[0].to_text()
    except dns.resolver.NoAnswer:
      logging.error("IP %s has no reverse records.", self.client_address)
      raise Exception("Access denied")
    # Check if we have host on the list of allowed hosts
    if client not in network_config.get('allowed_hosts', set([])):
      logging.warning("Client from %s tried to change network %s OSPF advertisment.", client, network)
      raise Exception("Access denied")

    return network_config

  def status(self, network):
    network = netaddr.IPNetwork(network)
    return 'enabled' if self._bird[network.version].has_network(network) else 'disabled'
