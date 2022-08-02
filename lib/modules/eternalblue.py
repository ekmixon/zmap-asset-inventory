#!/usr/bin/env python3

# by TheTechromancer

import sys
import ipaddress
from .base_module import *
import subprocess as sp
from datetime import datetime
import xml.etree.cElementTree as xml # for parsing Nmap output

class Module(BaseModule):

    name            = 'eternalblue'
    csv_headers     = ['Vulnerable to EternalBlue']
    required_ports  = [445]
    required_progs  = ['nmap']

    def __init__(self, inventory):

        super().__init__(inventory)

        self.process            = None
        self.targets_file       = str(self.work_dir / 'eternalblue_targets_{date:%Y-%m-%d_%H-%M-%S}'.format(date=datetime.now()))
        self.output_file        = str(self.work_dir / 'eternalblue_results_{date:%Y-%m-%d_%H-%M-%S}'.format(date=datetime.now()))


    def run(self, inventory):

        targets = 0
        with open(self.targets_file, mode='w') as f:
            for host in inventory:
                ip = host.ip
                try:
                    vulnerable = host['Vulnerable to EternalBlue']
                except KeyError:
                    vulnerable = 'N/A'
                inventory.hosts[ip].update({'Vulnerable to EternalBlue': vulnerable})

                if 445 in host.open_ports and vulnerable.strip().lower() not in {
                    'yes',
                    'no',
                }:
                    targets += 1
                    f.write(str(ip) + '\n')

        if targets <= 0:
            print('\n[!] No valid targets for EternalBlue scan')

        else:

            command = ['nmap', '-p445', '-T4', '-n', '-Pn', '-v', '-sV', \
                    '--script=smb-vuln-ms17-010', '-oA', self.output_file, \
                    '-iL', self.targets_file]

            print('\n[+] Scanning {:,} systems for EternalBlue:\n\t> {}\n'.format(targets, ' '.join(command)))

            try:
                self.process = sp.run(command, check=True)
            except sp.CalledProcessError as e:
                sys.stderr.write(f'[!] Error launching EternalBlue Nmap: {str(e)}\n')
                sys.exit(1)

            print('\n[+] Finished EternalBlue Nmap scan')

            # parse xml
            tree = xml.parse(f'{self.output_file}.xml')

            for host in tree.findall('host'):

                ip = None
                for address in host.findall('address'):
                    if address.attrib['addrtype'] == 'ipv4':
                        try:
                            ip = ipaddress.ip_address(address.attrib['addr'])
                        except ValueError:
                            continue
                        break

                if ip is None:
                    continue

                for hostscript in host.findall('hostscript'):
                    for script in hostscript.findall('script'):
                        if script.attrib['id'] == 'smb-vuln-ms17-010':
                            if 'VULNERABLE' in script.attrib['output']:
                                inventory.hosts[ip].update({'Vulnerable to EternalBlue': 'Yes'})
                            else:
                                inventory.hosts[ip].update({'Vulnerable to EternalBlue': 'No'})

            print(f'[+] Saved Nmap EternalBlue results to {self.output_file}.*')


    def report(self, inventory):

        vulnerable_hosts = []
        for host in inventory:
            try:
                if host['Vulnerable to EternalBlue'].lower().startswith('y'):
                    vulnerable_hosts.append(host)
            except KeyError:
                pass

        if vulnerable_hosts:
            print(
                f'[+] {len(vulnerable_hosts)} system(s) vulnerable to EternalBlue:\n\t',
                end='',
            )

            print('\n\t'.join([str(h) for h in vulnerable_hosts]))
        else:
            print('[+] No systems found vulnerable to EternalBlue')
        print('')


    def read_host(self, csv_line, host):

        try:
            vulnerable = csv_line['Vulnerable to EternalBlue']
        except KeyError:
            vulnerable = 'N/A'

        host.update({'Vulnerable to EternalBlue': vulnerable})