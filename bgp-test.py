#!/usr/bin/env python3

from mininet.node import CPULimitedHost, Host, Node
from mininet.node import OVSKernelSwitch, UserSwitch
from mininet.log import setLogLevel, info
from mininet.link import TCLink, Intf
from subprocess import call
import shutil
import time
from pathlib import Path
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.nodelib import LinuxBridge
import argparse

class LinuxRouter( Node ):
	def config( self, **params ):
		super( LinuxRouter, self).config( **params )
		self.cmd( 'sysctl -w net.ipv4.ip_forward=1' )
		self.cmd('/usr/lib/frr/zebra -A 127.0.0.1 -s 90000000 -f /etc/frr/frr.conf -d')
		self.cmd('/usr/lib/frr/staticd -A 127.0.0.1 -f /etc/frr/frr.conf -d')
		self.cmd('/usr/lib/frr/ospfd -A 127.0.0.1 -f /etc/frr/frr.conf -d')
		self.cmd('/usr/lib/frr/bgpd -A 127.0.0.1 -f /etc/frr/frr.conf -d')
		
		# region
		# self.cmd( 'sysctl -w net.ipv6.conf.all.forwarding=1' )
		# self.cmd('/usr/lib/frr/pimd -A 127.0.0.1 -f /etc/frr/frr.conf -d')
		# self.cmd('/usr/lib/frr/pim6d -A ::1 -f /etc/frr/frr.conf -d')
		# self.cmd('/usr/lib/frr/isisd -A 127.0.0.1 -f /etc/frr/frr.conf -d')
		# self.cmd('/usr/lib/frr/ospf6d -A ::1 -f /etc/frr/frr.conf -d')
		# endregion
		self.cmd('/usr/lib/frr/frr-reload.py  --reload /etc/frr/frr.conf')


	def terminate( self ):
		self.cmd( 'killall zebra staticd ospfd ospf6d bgpd pathd pimd pim6d ldpd isisd nhrpd vrrpd fabricd' )
		super( LinuxRouter, self ).terminate()

class OSPFLab(Topo):
	def generate_config(self, router_name, path):
		""" Generate an empty config for each router.\n
			path: the path of router configs directory
		"""
		router = {"name":router_name}
		path = path % router
		#print(path)
		#config template directory path
		template_path = Path("Template/router") 
		Path(path).mkdir(exist_ok=True, parents=True)

		#copy files from the config template folder
		for file in template_path.iterdir():
			shutil.copy(file, path)
		
		#modify hostname
		self.replace_hostname(path+"/frr.conf", "dummy", router_name)
		self.replace_hostname(path+"/vtysh.conf", "dummy", router_name)

		return
	
	def replace_hostname(self, filepath, toReplace, replacement):
		""" Replace hostname in a router config \n
			filepath: path to the config file\n
			toReplace: the hostname to replace\n
			replacement: the new hostname\n
		"""
		with open(filepath, 'r') as f:
			content = f.readlines()
			for linenum in range (len(content)):
				if (content[linenum] == "hostname "+toReplace+"\n"):
					content[linenum] = "hostname "+ replacement+"\n"
		with open(filepath, "w") as f:
			f.writelines(content)
		return	
	
	def parse_argument(self ):
		parser = argparse.ArgumentParser()
		parser.add_argument( "-g","--generateConfig", 
											help="Generate router config files.\n"
											+"This will overwrite existing files",
											action="store_true")
		parser.add_argument("-v", "--verbose", 
											help="Prints detailed logs during network creation and stop",
											action="store_true")
		parser.add_argument("-c", "--config",
											help="Specify the directory to use for saving the configurations \
												(default: ./config_ospf_lab) \n\
												Example: \"sudo python3 ospf-lab.py -c /tmp/config_ospf_lab\"",
											dest="config_dir",
											default="config_ospf_lab")
		flags = parser.parse_args()
		if flags.config_dir == "":
			raise argparse.ArgumentTypeError("directory cannot be an empty string. Use -h to see examples")
			# throw error here
		elif flags.config_dir.isspace():
			raise argparse.ArgumentTypeError("directory cannot be only whitespace. Use -h to see examples")

		# print(flags)

		return flags
	
	def build(self, *args, **kwargs):
		flags = self.parse_argument()
		if(flags.verbose):
			setLogLevel( 'info' )
		
		# directory to keep the configurations
		# config_path = "/tmp/config_ospf_lab/%(name)s"
		config_path = flags.config_dir+"/%(name)s"
		print(config_path)
		
		# private directory that will useed by the routers by bind mounting
		privateDirs = [ ( '/var/log' ),
						( '/etc/frr', config_path),
						( '/var/run' ),
						'/var/mn' ]
		
		# AS100
		C11 = self.addHost('C11', ip="172.16.1.2/24", defaultRoute="via 172.16.1.1")
		R11 = self.addNode("R11", cls=LinuxRouter, ip="10.11.0.1/32", privateDirs=privateDirs, inNamespace=True)
		R12 = self.addNode("R12", cls=LinuxRouter, ip="10.11.0.2/32", privateDirs=privateDirs, inNamespace=True)
		R13 = self.addNode("R13", cls=LinuxRouter, ip="10.11.0.3/32", privateDirs=privateDirs, inNamespace=True)
		R14 = self.addNode("R14", cls=LinuxRouter, ip="10.11.0.4/32", privateDirs=privateDirs, inNamespace=True)
		S11 = self.addSwitch("S11", inNamespace=True)

		# Add links with IP addresses
		self.addLink(S11, R12, intfName2='R12-eth0', params2={'ip': '172.16.1.1/24'})
		self.addLink(S11, C11)

		self.addLink(R11, R12, intfName1='R11-eth0', params1={'ip': '10.11.1.1/24'},
								intfName2='R12-eth1', params2={'ip': '10.11.1.2/24'})
		self.addLink(R11, R13, intfName1='R11-eth1', params1={'ip': '10.11.2.1/24'},
								intfName2='R13-eth0', params2={'ip': '10.11.2.2/24'})
		self.addLink(R12, R14, intfName1='R12-eth2', params1={'ip': '10.11.3.1/24'},
								intfName2='R14-eth0', params2={'ip': '10.11.3.2/24'})
		self.addLink(R13, R14, intfName1='R13-eth1', params1={'ip': '10.11.4.1/24'},
								intfName2='R14-eth1', params2={'ip': '10.11.4.2/24'})

		# AS200
		C22 = self.addHost('C22', ip="172.17.1.2/24", defaultRoute="via 172.17.1.1")
		R21 = self.addNode("R21", cls=LinuxRouter, ip="10.12.0.1/32", privateDirs=privateDirs, inNamespace=True)
		R22 = self.addNode("R22", cls=LinuxRouter, ip="10.12.0.2/32", privateDirs=privateDirs, inNamespace=True)
		R23 = self.addNode("R23", cls=LinuxRouter, ip="10.12.0.3/32", privateDirs=privateDirs, inNamespace=True)
		R24 = self.addNode("R24", cls=LinuxRouter, ip="10.12.0.4/32", privateDirs=privateDirs, inNamespace=True)
		S22 = self.addSwitch("S22", inNamespace=True)

		self.addLink(S22, R21, intfName2='R21-eth0', params2={'ip': '172.17.1.1/24'})
		self.addLink(S22, C22)

		self.addLink(R21, R22, intfName1='R21-eth1', params1={'ip': '10.12.1.1/24'},
								intfName2='R22-eth0', params2={'ip': '10.12.1.2/24'})
		self.addLink(R21, R23, intfName1='R21-eth2', params1={'ip': '10.12.2.1/24'},
								intfName2='R23-eth0', params2={'ip': '10.12.2.2/24'})
		self.addLink(R22, R24, intfName1='R22-eth1', params1={'ip': '10.12.3.1/24'},
								intfName2='R24-eth0', params2={'ip': '10.12.3.2/24'})
		self.addLink(R23, R24, intfName1='R23-eth1', params1={'ip': '10.12.4.1/24'},
								intfName2='R24-eth1', params2={'ip': '10.12.4.2/24'})

		# AS300
		C33 = self.addHost('C33', ip="172.18.1.2/24", defaultRoute="via 172.18.1.1")
		R31 = self.addNode("R31", cls=LinuxRouter, ip="10.13.0.1/32", privateDirs=privateDirs, inNamespace=True)
		R32 = self.addNode("R32", cls=LinuxRouter, ip="10.13.0.2/32", privateDirs=privateDirs, inNamespace=True)
		R33 = self.addNode("R33", cls=LinuxRouter, ip="10.13.0.3/32", privateDirs=privateDirs, inNamespace=True)
		R34 = self.addNode("R34", cls=LinuxRouter, ip="10.13.0.4/32", privateDirs=privateDirs, inNamespace=True)
		S33 = self.addSwitch("S33", inNamespace=True)

		self.addLink(S33, R33, intfName2='R33-eth0', params2={'ip': '172.18.1.1/24'})
		self.addLink(S33, C33)

		self.addLink(R31, R32, intfName1='R31-eth0', params1={'ip': '10.13.1.1/24'},
								intfName2='R32-eth0', params2={'ip': '10.13.1.2/24'})
		self.addLink(R31, R33, intfName1='R31-eth1', params1={'ip': '10.13.2.1/24'},
								intfName2='R33-eth1', params2={'ip': '10.13.2.2/24'})
		self.addLink(R32, R34, intfName1='R32-eth1', params1={'ip': '10.13.3.1/24'},
								intfName2='R34-eth0', params2={'ip': '10.13.3.2/24'})
		self.addLink(R33, R34, intfName1='R33-eth2', params1={'ip': '10.13.4.1/24'},
								intfName2='R34-eth1', params2={'ip': '10.13.4.2/24'})

		# eBGP Links between ASes
		self.addLink(R14, R21, intfName1='R14-eth2', params1={'ip': '10.100.1.1/24'},
								intfName2='R21-eth3', params2={'ip': '10.100.1.2/24'})
		self.addLink(R24, R31, intfName1='R24-eth2', params1={'ip': '10.100.2.1/24'},
								intfName2='R31-eth2', params2={'ip': '10.100.2.2/24'})

		# iBGP logical link for AS100 (loopback IPs)
		self.addLink(R11, R14, intfName1='R11-lo', intfName2='R14-lo')

		# In this setup, the iBGP connection between R11 and R14 uses "loopback" addresses set manually in the CLI.

		
		confdir = Path(config_path % {"name": ""})
		if (not flags.generateConfig):
			if (not Path.exists(confdir)):
				# Automatically set to generate config files if config Path doesn't exists, such as when first time running the program
				print("If this is your first time running the program, ")
				print("consider running the program with \"-h\" to see the options")
				print("="*40)
				flags.generateConfig=True
				
		if (flags.generateConfig):
			# Configuration files will be created for each routers
			for n in self.nodes():
				print(n)
				if "cls" in self.nodeInfo(n):
					node_info = self.nodeInfo(n)
					if node_info["cls"].__name__ == "LinuxRouter":
						self.generate_config(n, config_path)
						pass

		super().build(*args, **kwargs)

start = time.time()
print("This the topology for the OSPF lab")
print("="*40)
net = Mininet(topo=OSPFLab(), switch=LinuxBridge, controller=None)
finish = time.time()
print("Finished initializing network in:", finish-start, "seconds")

try:
	pass
	net.start()
	CLI(net)
	
finally:
	start = time.time()
	net.stop()
	finish = time.time()
	print("Finished stopping network in:", finish-start, "seconds")
