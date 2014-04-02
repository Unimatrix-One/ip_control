from ConfigParser import RawConfigParser

# For access from other modules
config = None

def init(config_file):
  global config
  config = RawConfigParser({
    'General': {
    }
  })
  config.readfp(open(config_file, 'r'))
  return config

def write_example():
    print """[General]
# DNS name for list of all ip controllers
ip_control_dns_name = ip.control.services.uninet
# Bird configuration file we are editing
bird4_dynamic_config = /var/cache/bird/dynamic_ipv4.conf
# Bird reload command (make sure to config sudoers)
bird4_reload = sudo service bird reload
# Bird6 configuration file we are editing
bird6_dynamic_config = /var/cache/bird/dynamic_ipv6.conf
# Bird6 reload command (make sure to config sudoers)
bird6_reload = sudo service bird6 reload
# Command to be executed when adding route
add_route = sudo ip ro add {network} dev {interface}
# Command to be executed when removing route
remove_route = sudo ip ro add {network} dev {interface}
# Command to be executed when checking IPv4 route
ipv4_check_route = ip ro sh dev {interface} | grep "scope link" | grep {network}
# Command to be executed when checking IPv6 route
ipv6_check_route = ip -6 ro sh dev {interface} | grep "scope link" | grep {network}
# A file for checking persistance, if file doesn't exist
# it will revert all previously enabled routes and
# create this file for ensuring persistance after restart.
# Make sure this file gets removed upon machine restart
persistance_file = /tmp/persistant-routes

# A section dedicated to a specific IP network
[10.2.xxx.xxx/32]
# Allowed hosts to manage this IP
allowed_hosts=ctxxxx.dronexx.tus.uninet,
              ctxxxx.dronexx.tus.uninet
# Is IP unicasted? (usable only for /32 or /128)
unicast = false
# Interface to add route to
interface = lxc0
"""
