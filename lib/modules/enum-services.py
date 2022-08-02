#!/usr/bin/env python3

# by TheTechromancer

import os
import sys
import json
import random
import ipaddress
import configparser
from time import sleep
import subprocess as sp
from shutil import which
from pathlib import Path
import concurrent.futures
from datetime import datetime
from .base_module import *


class ServiceEnumException(Exception):
    pass

class LogonFailureException(Exception):
    pass



class Module(BaseModule):

    name            = 'enum_services'
    csv_headers     = []
    required_ports  = [445]
    required_progs  = ['wmiexec.py']



    def __init__(self, inventory):

        super().__init__(inventory)

        self.config = self.parse_config()
        self.lockout_counter = 0

        # {ip : 'wmiexec_output'}
        self.raw_wmiexec_output = {}
        # {ip: {service: 'Yes'}}
        self.services = {}

        self.raw_output_file = self.work_dir / 'raw_wmiexec_output_{date:%Y-%m-%d_%H-%M-%S}.txt'.format( date=datetime.now() )



    def run(self, inventory):

        try:
            # set up threading
            futures = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:

                hosts_to_scan = [h for h in inventory if 445 in h.open_ports]

                if not hosts_to_scan:
                    print('\n[+] No valid targets for service enumeration')

                else:
                    print('\n[+] Retrieving service information for {:,} Windows hosts'.format(len(hosts_to_scan)))
                    # shuffle hosts
                    hosts_to_scan = random.sample(hosts_to_scan, len(hosts_to_scan))

                    for host in hosts_to_scan:
                        assert self.lockout_counter < self.ufail_limit
                        futures.append(executor.submit(self.get_services, host))
                        sleep(.75)

                    sleep(10)
                    executor.shutdown(wait=True)

                    for ip, services in self.services.items():
                        inventory.hosts[ip].update(services)


        except AssertionError:
            print('[!] Logon failure limit reached ({limit}/{limit})'.format(limit=self.ufail_limit))

        finally:
            try:
                if hosts_to_scan:
                    print(f'[+] Writing raw command output to {self.raw_output_file}')
                    with open(self.raw_output_file, 'w') as f:
                        for ip, output in self.raw_wmiexec_output.items():
                            f.write(str(ip) + '\n')
                            f.write('*' * 5 + '\n')
                            f.write(str(output) + '\n')
                            f.write('=' * 5 + '\n')
            except NameError:
                pass


    def get_services(self, host):

        ip = host.ip

        w = wmiexec(host, self.config)
        try:
            result = w.get_services()
        except ServiceEnumException as e:
            print(f'[!] Error getting services from {str(host)}')
            print(e)
            return
        except LogonFailureException as e:
            print(f'[!] LOGIN FAILURE ON {str(host)}')
            print(e)
            # increment lockout counter
            self.lockout_counter += 1
            return

        if result:
            # reset lockout counter
            self.lockout_counter = 0

            os_name, services_detected = result

            print('[+] Found {:,} services on {}'.format(list(services_detected.values()).count('Yes'), ip))

            self.services[ip] = {'OS': os_name}
            self.services[ip].update(services_detected)

            self.raw_wmiexec_output[ip] = w.raw_stdout + w.raw_stderr

        else:
            print(f'[!] No output returned from service enumeration of {str(self)}')




    def report(self, inventory):

        os_stats = {}
        service_stats = {}

        service_stats_workstations = {}
        service_stats_servers = {}

        hosts_total = 0
        workstations_total = 0
        servers_total = 0

        service_names = list(self.config['SERVICES'].items())

        for host in inventory:
            try:
                os = host['OS']
                if os.lower() != 'unknown':
                    try:
                        os_stats[os] += 1
                    except KeyError:
                        os_stats[os] = 1

                for fname,sname in service_names:
                    host_has_service = host[fname]

                    if host_has_service.lower().startswith('y'):
                        try:
                            service_stats[fname] += 1
                        except KeyError:
                            service_stats[fname] = 1

                        if 'server' in os.lower():
                            try:
                                service_stats_servers[fname] += 1
                            except KeyError:
                                service_stats_servers[fname] = 1
                        else:
                            try:
                                service_stats_workstations[fname] += 1
                            except KeyError:
                                service_stats_workstations[fname] = 1

                hosts_total += 1
                if 'server' in os.lower():
                    servers_total += 1
                else:
                    workstations_total += 1

            except KeyError as e:
                continue

        if hosts_total > 0:

            report = []

            report.append('SERVICES:')

            service_stats = list(service_stats.items())
            service_stats.sort(key=lambda x: x[1], reverse=True)

            service_stats_servers = list(service_stats_servers.items())
            service_stats_servers.sort(key=lambda x: x[1], reverse=True)

            service_stats_workstations = list(service_stats_workstations.items())
            service_stats_workstations.sort(key=lambda x: x[1], reverse=True)

            def divide(a, b):
                try:
                    return a / b
                except ZeroDivisionError:
                    return 0

            report.append('\tGlobal:')
            for service, count in service_stats:
                report.append('\t\t{}: {:,}/{:,} ({:.1f}%)'.format(service, count, hosts_total, divide(count, hosts_total)*100))
            for service_name in service_names:
                if service_name[0] not in [s[0] for s in service_stats]:
                    report.append('\t\t{}: 0/{} (0.0%)'.format(service_name[0], hosts_total))

            report.append('\tWorkstations:')
            for service, count in service_stats_workstations:
                report.append('\t\t{}: {:,}/{:,} ({:.1f}%)'.format(service, count, workstations_total, divide(count, workstations_total)*100))
            for service_name in service_names:
                if service_name[0] not in [s[0] for s in service_stats_workstations]:
                    report.append('\t\t{}: 0/{} (0.0%)'.format(service_name[0], workstations_total))

            report.append('\tServers:')
            for service, count in service_stats_servers:
                report.append('\t\t{}: {:,}/{:,} ({:.1f}%)'.format(service, count, servers_total, divide(count, servers_total)*100))
            for service_name in service_names:
                if service_name[0] not in [s[0] for s in service_stats_servers]:
                    report.append('\t\t{}: 0/{} (0.0%)'.format(service_name[0], servers_total))

            report.append('\nOPERATING SYSTEMS:')
            os_stats = list(os_stats.items())
            os_stats.sort(key=lambda x: x[1], reverse=True)
            for os, count in os_stats:
                report.append('\t{}: {:,}/{:,} ({:.1f}%)'.format(os, count, hosts_total, divide(count, hosts_total)*100))

            print('\n'.join(report))
            print('')



    def read_host(self, line, host):

        service_friendly_names = [i.lower() for i in list(self.services.values())]

        # update host if the line header matches one of the services in services.config
        for key, value in line.items():
            if key.lower() in service_friendly_names:
                host.update({key: value})



    def parse_config(self):

        try:

            config_path = "{0}/services.config".format(sys.path[0])
            config = configparser.ConfigParser()
            config.read(config_path)

            if not config:
                raise KeyError('Error parsing config file')

            self.threads = int(config['EXECUTION']['THREADS'])
            self.ufail_limit = int(config['CREDENTIALS']['consecutivefailedlogonlimit'])

            # make sure we have credentials
            if not config['CREDENTIALS']['username'] or not (config['CREDENTIALS']['password'] \
                    or config['CREDENTIALS']['hashes']):
                try:
                    ticket_var = Path(os.environ['KRB5CCNAME'])
                    ticket = True
                except KeyError:
                    print('[!] Username or password missing and no KRB5CCNAME variable found.')
                    return

            self.csv_headers = list(config['SERVICES'].keys())
            if self.csv_headers:
                self.csv_headers = ['OS'] + self.csv_headers
            else:
                raise TypeError('No services specified in services.config')

            return config

        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f'Problem with services.config at {str(config_file)}')





class wmiexec:
    '''
    Can be used with any of the impacket execution methods (smbexec, atexec, etc.)
    '''

    def __init__(self, target, config):

        self.target   = target.ip
        self.username = config['CREDENTIALS']['username']
        self.password = config['CREDENTIALS']['password']
        self.domain   = config['CREDENTIALS']['domain']
        self.hashes   = config['CREDENTIALS']['hashes']
        self.services = config['SERVICES']
        self.timeout  = int(config['EXECUTION']['TIMEOUT'])
        self.method   = config['EXECUTION']['METHOD']

        self.impacket_auth = ''

        self.raw_output = ''

        self.ticket = False
        if not self.username or not (self.password or self.hashes):
            try:
                os.environ['KRB5CCNAME']
                if target.hostname:
                    self.target = target.hostname
                else:
                    raise ValueError(
                        f"Ticket authentication needs valid hostname, none found for {str(target['IP Address'])}, skipping"
                    )

                self.impacket_auth = [
                    '-k',
                    '-no-pass',
                    f'{self.domain}/{self.username}@{str(self.target)}',
                ]

            except KeyError:
                raise ValueError('Kerberos ticket not found, please export "KRB5CCNAME" variable')
        elif self.password:
            self.impacket_auth = [
                f'{self.domain}/{self.username}:{self.password}@{self.target}'
            ]

        else:
            self.impacket_auth = [
                '-hashes',
                self.hashes,
                f'{self.domain}/{self.username}@{self.target}',
            ]



    def get_services(self):
        '''
        enumerates requested services
        returns tuple (os_name, { service_fname: True|False ... } )
        '''

        service_keywords = set()
        for service_name in self.services.values():
            [service_keywords.add(word) for word in service_name.split()]

        canary = '!@#'
        canary_cmd = f'echo {canary}'

        win_commands = [
            '(',
            canary_cmd,
            '&',
            '''reg query "hklm\\software\\microsoft\\windows nt\\currentversion" /v productname''',
            '&',
            canary_cmd,
            '&',
            f'''sc query | findstr /i "{' '.join(service_keywords)}"''',
            ')',
        ]


        stdout,stderr = self.run_wmiexec(' '.join(win_commands))

        if 'STATUS_LOGON_FAILURE' in stdout:
            raise LogonFailureException(stdout + stderr)
        elif canary not in stdout:
            raise ServiceEnumException(stdout + stderr)

        else:
            try:
                os_str, svc_str = [[line.strip() for line in chunk.split('\r\n') if line.strip()] for chunk in stdout.split(canary)[1:3]]
            except ValueError:
                raise ServiceEnumException(stdout + stderr)

        os_name = ' '.join(os_str[-1].split()[2:])

        services_detected = {}
        for (fname, sname) in self.services.items():
            sname = sname.upper()

            services_detected[fname] = 'No'

            for s in svc_str:
                svc_name = ':'.join(s.split(':')[1:]).strip().upper()
                if sname in svc_name:
                    services_detected[fname] = 'Yes'
                    break

        return (os_name, services_detected)



    def run_wmiexec(self, command, method=None, timeout=None):

        if timeout is None:
            timeout = self.timeout

        if method is None:
            method = self.method

        exec_base = [method] + self.impacket_auth
        exec_command = exec_base + [command]

        print(' >> ' + ' '.join(exec_base) + f" '{command}'")
        try:
            env = dict(os.environ, PYTHONIOENCODING='UTF-8')
            exec_process = sp.run(exec_command, stdout=sp.PIPE, stderr=sp.PIPE, timeout=timeout, env=env)
            self.raw_stdout = exec_process.stdout.decode()
            self.raw_stderr = exec_process.stderr.decode()
            return (self.raw_stdout, self.raw_stderr)
        except sp.TimeoutExpired:
            raise ServiceEnumException(f'{method} timed out:\n{" ".join(exec_command)}')
