#!/usr/bin/env python3

# by TheTechromancer

import sys
import ipaddress
from time import sleep
import subprocess as sp
import concurrent.futures
from .base_module import *
from datetime import datetime
import xml.etree.cElementTree as xml # for parsing Nmap output

class Module(BaseModule):

    name            = 'open-shares'
    csv_headers     = ['Open FTP', 'Open NFS'] #'Open SMB',
    required_ports  = [21,111,9100] #139,445
    required_progs  = ['nmap']

    def __init__(self, inventory):

        super().__init__(inventory)



    def run(self, inventory):

        '''
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(self.check_smb, inventory)
            sleep(1)
            executor.submit(self.check_ftp, inventory)
            sleep(1)
            executor.submit(self.check_nfs, inventory)
        '''
        #self.check_smb(inventory)
        self.check_ftp(inventory)
        self.check_nfs(inventory)




    def check_ftp(self, inventory):

        targets = 0
        targets_file       = str(self.work_dir / 'ftp_targets_{date:%Y-%m-%d_%H-%M-%S}'.format(date=datetime.now()))
        output_file        = str(self.work_dir / 'ftp_results_{date:%Y-%m-%d_%H-%M-%S}'.format(date=datetime.now()))

        with open(targets_file, 'w') as f:
            for host in inventory:
                try:
                    if host['Open FTP'].lower() in ['yes', 'no']:
                        continue
                except KeyError:
                    pass
                if 9100 not in host.open_ports and 21 in host.open_ports:
                    f.write(str(host.ip) + '\n')
                    targets += 1

        if targets <= 0:
            print('\n[!] No valid targets for FTP scan')

        else:

            command = ['nmap', '-p21', '-T4', '-n', '-Pn', '-v', '-sV', \
                    '--script=ftp-anon', '-oA', output_file, \
                    '-iL', targets_file]

            print('\n[+] Scanning {:,} system(s) for open FTP:\n\t> {}\n'.format(targets, ' '.join(command)))

            try:
                process = sp.run(command, check=True)
            except sp.CalledProcessError as e:
                sys.stderr.write(f'[!] Error launching Nmap FTP scan: {str(e)}\n')
                return

            # parse xml
            tree = xml.parse(f'{output_file}.xml')

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

                inventory.hosts[ip].update({'Open FTP': 'No'})

                for nmap_ports in host.findall('ports'):
                    for nmap_port in nmap_ports.findall('port'):
                        for script in nmap_port.findall('script'):
                            if (
                                script.attrib['id'] == 'ftp-anon'
                                and 'Anonymous FTP login allowed'
                                in script.attrib['output']
                            ):
                                inventory.hosts[ip].update({'Open FTP': 'Yes'})


            print(f'[+] Saved Nmap FTP scan results to {output_file}.*')
            print('\n[+] Finished Nmap FTP scan')




    def check_smb(self, inventory):

        targets = 0
        targets_file       = str(self.work_dir / 'smb_targets_{date:%Y-%m-%d_%H-%M-%S}'.format(date=datetime.now()))
        output_file        = str(self.work_dir / 'smb_results_{date:%Y-%m-%d_%H-%M-%S}'.format(date=datetime.now()))

        with open(targets_file, 'w') as f:
            for host in inventory:
                try:
                    if host['Open SMB'].lower() in ['yes', 'no']:
                        continue
                except KeyError:
                    pass
                if 9100 not in host.open_ports and any(
                    port in host.open_ports for port in [139, 445]
                ):
                    f.write(str(host.ip) + '\n')
                    targets += 1

        if targets <= 0:
            print('\n[!] No valid targets for SMB scan')

        else:

            command = ['nmap', '-p139,445', '-T4', '-n', '-Pn', '-v', '-sV', \
                    '--script=smb-enum-shares', '-oA', output_file, \
                    '-iL', targets_file]

            print('\n[+] Scanning {:,} system(s) for open SMB:\n\t> {}\n'.format(targets, ' '.join(command)))

            try:
                process = sp.run(command, check=True)
            except sp.CalledProcessError as e:
                sys.stderr.write(f'[!] Error launching Nmap SMB scan: {str(e)}\n')
                return

            print('\n[+] Finished Nmap SMB scan')

            # parse xml
            tree = xml.parse(f'{output_file}.xml')

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

                inventory.hosts[ip].update({'Open SMB': 'No'})

                for hostscript in host.findall('hostscript'):
                    for script in hostscript.findall('script'):
                        if script.attrib['id'] == 'smb-enum-shares' and any(
                            keyword in script.attrib['output']
                            for keyword in ['access: READ', 'access: WRITE']
                        ):
                            inventory.hosts[ip].update({'Open SMB': 'Yes'})


            print(f'[+] Saved Nmap SMB results to {output_file}.*')
            print('\n[+] Finished Nmap SMB scan')



    def check_nfs(self, inventory):

        targets = 0
        targets_file       = str(self.work_dir / 'nfs_targets_{date:%Y-%m-%d_%H-%M-%S}'.format(date=datetime.now()))
        output_file        = str(self.work_dir / 'nfs_results_{date:%Y-%m-%d_%H-%M-%S}'.format(date=datetime.now()))

        with open(targets_file, 'w') as f:
            for host in inventory:
                try:
                    if host['Open NFS'].lower() in ['yes', 'no']:
                        continue
                except KeyError:
                    pass
                if 111 in host.open_ports:
                    f.write(str(host.ip) + '\n')
                    targets += 1

        if targets <= 0:
            print('\n[!] No valid targets for NFS scan')

        else:

            command = ['nmap', '-p111', '-T4', '-n', '-Pn', '-v', '-sV', \
                    '--script=nfs-showmount', '-oA', output_file, \
                    '-iL', targets_file]

            print('\n[+] Scanning {:,} system(s) for open NFS:\n\t> {}\n'.format(targets, ' '.join(command)))

            try:
                process = sp.run(command, check=True)
            except sp.CalledProcessError as e:
                sys.stderr.write(f'[!] Error launching Nmap NFS scan: {str(e)}\n')
                return

            # parse xml
            tree = xml.parse(f'{output_file}.xml')

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

                inventory.hosts[ip].update({'Open NFS': 'No'})

                for nmap_ports in host.findall('ports'):
                    for nmap_port in nmap_ports.findall('port'):
                        for script in nmap_port.findall('script'):
                            if (
                                script.attrib['id'] == 'nfs-showmount'
                                and '/' in script.attrib['output']
                            ):
                                inventory.hosts[ip].update({'Open NFS': 'Yes'})


            print(f'[+] Saved Nmap NFS scan results to {output_file}.*')
            print('\n[+] Finished Nmap NFS scan')



    def report(self, inventory):

        vulnerable_hosts = []
        for host in inventory:
            try:
                if host['Open NFS'].lower().startswith('y'):
                    vulnerable_hosts.append(host)
            except KeyError:
                pass

        if vulnerable_hosts:
            print(
                f'[+] {len(vulnerable_hosts)} system(s) with open NFS shares:\n\t',
                end='',
            )

            print('\n\t'.join([str(h) for h in vulnerable_hosts]))
        else:
            print('[+] No systems found with open NFS shares')
        print('')

        '''
        vulnerable_hosts = []
        for host in inventory:
            try:
                if host['Open SMB'].lower().startswith('y'):
                    vulnerable_hosts.append(host)
            except KeyError:
                pass

        if vulnerable_hosts:
            print('[+] {} system(s) with open SMB shares:\n\t'.format(len(vulnerable_hosts)), end='')
            print('\n\t'.join([str(h) for h in vulnerable_hosts]))
        else:
            print('[+] No systems found with open SMB shares')
        print('')
        '''

        vulnerable_hosts = []
        for host in inventory:
            try:
                if host['Open FTP'].lower().startswith('y'):
                    vulnerable_hosts.append(host)
            except KeyError:
                pass

        if vulnerable_hosts:
            print(f'[+] {len(vulnerable_hosts)} system(s) with open FTP:\n\t', end='')
            print('\n\t'.join([str(h) for h in vulnerable_hosts]))
        else:
            print('[+] No systems with open FTP')
        print('')



    def read_host(self, csv_line, host):

        vulnerable = 'N/A'
        try:
            vulnerable = csv_line['Open SMB'].strip()
        except KeyError:
            pass
        host.update({'Open SMB': vulnerable})

        vulnerable = 'N/A'
        try:
            vulnerable = csv_line['Open FTP'].strip()
        except KeyError:
            pass
        host.update({'Open FTP': vulnerable})

        vulnerable = 'N/A'
        try:
            vulnerable = csv_line['Open NFS'].strip()
        except KeyError:
            pass
        host.update({'Open NFS': vulnerable})