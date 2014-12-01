IP-Control
==========

A simple daemon with JSON-RPC API for controlling IP networks
and routes. It adds/removes network directives from BIRD
configuration and reloads it.

You may use IP-Control to manage network in CIDR notation, or
manage unicasted IP address (network with /32).

Use case
--------

With API
++++++++

On our infrastructure we have PostgreSQL with WAL replication
and PgPool for managing the replication. All four services are
in separate containers on four different servers and are not
on the same subnet so the built-in PgPool watchdog cannot work.
With IP-Control you can disable or enable /32 route for pgpool
virtual IP.

With healthcheck
++++++++++++++++

IP-Control has built in healthcheck logic, through config you
can specify custom script to test for availability of a service.
If service is disabled it will disable the network.

RPC API
-------

With RPC API you can check status of an network and enable or
disable it.

status(network)
+++++++++++++++

Checks if specific network is enabled. Returns 'enabled' or
'disabled'.

enable(network)
+++++++++++++++

Enables the network. If network is specified as unicast, it will
send disable commands to other IP-Control daemons.

disable(network)
++++++++++++++++

Disables the network.

DNS
---

IP-Control daemons know of each other through DNS. Your machine
needs to have a resolvable FQDN (also with PTR record). Port
number is then set by resolving of TXT record of a control
domain specified in config. The TXT record has to be specified
as 'port=<port_number>'. This ensures all IP-Control daemons
are on same port in the same control group (cross control group
communication is currently unsupported).

Config
------

On info about config directives, take a look at:

::

  ip-control --example-cfg

