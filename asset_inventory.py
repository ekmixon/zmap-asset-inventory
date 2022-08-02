#!/usr/bin/env python3

# by TheTechromancer

'''
TODO:
    - check domain when getting services
        - also check for multi-homed systems / jumpboxes?
'''

import os
import csv
import sys
import string
import argparse
import importlib
import ipaddress
from pathlib import Path
from datetime import datetime
from lib.host import *
from lib.deliverable import *
from lib.inventory import Inventory


# detect .py modules in lib/modules
detected_modules = []

script_location = Path(__file__).resolve().parent
module_candidates = next(os.walk(script_location / 'lib/modules'))[2]

for file in module_candidates:
    file = Path(file)
    if file.suffix == ('.py') and file.stem not in ['__init__', 'base_module']:
        detected_modules.append(str(file.stem))



def main(options):

    # make sure blacklist and whitelist exist
    if options.blacklist:
        assert Path(options.blacklist).resolve().is_file(), 'Problem reading blacklist file "{}"'.format(str(options.blacklist))
    if options.whitelist:
        assert Path(options.whitelist).resolve().is_file(), 'Problem reading whitelist file "{}"'.format(str(options.whitelist))

    # create working directory
    options.work_dir = options.work_dir.resolve()
    cache_dir = options.work_dir / 'cache'

    # if starting fresh, rename working directory to ".bak"
    if options.start_fresh:
        backup_cache_dir = Path(str(cache_dir) + '_{date:%Y-%m-%d_%H-%M-%S}.bak'.format( date=datetime.now() ))
        try:
            old_dir = str(cache_dir)
            cache_dir.rename(backup_cache_dir)
            print('[+] Backed up {} to {}'.format(old_dir, str(backup_cache_dir)))
        except FileNotFoundError:
            pass

    zmap_dir = cache_dir / 'zmap'
    zmap_dir.mkdir(mode=0o755, parents=True, exist_ok=True)

    if options.csv_file is None:
        options.csv_file = options.work_dir / 'asset_inventory_{date:%Y-%m-%d_%H-%M-%S}.csv'.format( date=datetime.now() )


    z = Inventory(options.targets, options.bandwidth, resolve=(not options.no_dns), force_resolve=options.force_dns, \
        work_dir=cache_dir, skip_ping=options.skip_ping, force_ping=options.force_ping, force_syn=options.force_syn, \
        blacklist=options.blacklist, whitelist=options.whitelist, interface=options.interface, \
        gateway_mac=options.gateway_mac)

    def load_module(m, active=False):
        z.modules.append(m)
        if active:
            z.active_modules.append(m)
            try:
                options.ports += m.required_ports
            except TypeError:
                options.ports = m.required_ports

    for module in detected_modules:
        module_name = 'lib.modules.{}'.format(module)
        try:
            #_m = importlib.import_module(module_name, package=__package__)
            _m = importlib.import_module(module_name)
            m = _m.Module(z)
            load_module(m, active=(module in options.modules))
        except ImportError as e:
            sys.stderr.write('[!] Error importing {}:\n{}\n'.format(module_name, str(e)))
            continue


    # load cached hosts
    z.load_scan_cache()


    # do host discovery
    for host in z:
        pass


    # scan additional ports if requested
    # only alive hosts are scanned
    if options.ports:

        # deduplicate ports
        options.ports = list(set(options.ports))

        # always scan 445 first so AV will have less of a chance to block us
        if 445 in options.ports:
            options.ports.remove(445)
            options.ports = [445] + options.ports

        for port in options.ports:
            zmap_out_file, new_hosts_found = z.scan_online_hosts(port)
            if new_hosts_found:
                print('\n[+] Port scan results for {}/TCP written to {}'.format(port, zmap_out_file))


    # run modules
    z.run_modules()


    # write CSV file
    try:
        z.write_csv(csv_file=options.csv_file)
    except PermissionError as e:
        pass

    # print summary
    z.report(netmask=options.netmask)

    # print module reports
    z.module_reports()

    # calculate deltas if requested
    if options.diff:
        stray_hosts = []
        stray_networks = []

        stray_networks = z.get_network_delta(options.diff, netmask=options.netmask)
        stray_networks_csv = './network_diff_{date:%Y-%m-%d_%H-%M-%S}.csv'.format( date=datetime.now())
        print('')
        print('[+] {:,} active network(s) not found in {}'.format(len(stray_networks), str(options.diff)))
        print('[+] Full report written to {}'.format(stray_networks_csv))
        print('=' * 60)

        with open(stray_networks_csv, 'w', newline='') as f:
            csv_file = csv.DictWriter(f, fieldnames=['Network', 'Host Count'])
            csv_file.writeheader()

            max_display_count = 20
            for network in stray_networks:
                #print('\t{:<16}{}'.format(str(network[0]), network[1]))
                print('\t{:<19}{:<10}'.format(str(network[0]), ' ({:,})'.format(network[1])))
                max_display_count -= 1
                if max_display_count <= 0:
                    print('\t...')
                    break

            for network in stray_networks:
                csv_file.writerow({'Network': str(network[0]), 'Host Count': str(network[1])})

        stray_hosts = z.get_host_delta(options.diff)
        stray_hosts_csv = './host_diff_{date:%Y-%m-%d_%H-%M-%S}.csv'.format( date=datetime.now())
        print('')
        print('[+] {:,} alive host(s) not found in {}'.format(len(stray_hosts), str(options.diff)))
        print('[+] Full report written to {}'.format(stray_hosts_csv))
        print('=' * 60)

        max_display_count = 20
        for host in stray_hosts:
            print('\t{}'.format(str(host)))
            max_display_count -= 1
            if max_display_count <= 0:
                print('\t...')
                break

        z.write_csv(csv_file=stray_hosts_csv, hosts=stray_hosts)

        # if more than 5 percent of hosts are strays, or you have more than one stray network
        if len(z.hosts) > 0 and (
            len(stray_hosts) / len(z.hosts) > 0.05 or len(stray_networks) > 1
        ):
            print('')
            print(' "Your asset management is bad and you should feel bad"')
            print('\n')


    # make a deliverable spreadsheet if requested
    if options.make_deliverable:

        print('[+] Combining all data gathered to date for specified targets:')
        print('     - {}'.format('\n     - '.join([str(t) for t in options.targets])))

        csv_files = []
        try:
            for csv_file in next(os.walk(options.work_dir))[2]:
                if csv_file.startswith('asset_inventory') and csv_file.endswith('.csv'):
                    print('[+] Found asset inventory CSV: {}'.format(csv_file))
                    csv_files.append(options.work_dir / csv_file)

        except StopIteration:
            pass

        filename = options.work_dir / 'asset_inventory_deliverable_{date:%Y-%m-%d_%H-%M-%S}.csv'.format( date=datetime.now() )

        deliverable = Deliverable(z, csv_files)
        deliverable.generate_xlsx(filename)

    print('[+] CSV file written to {}'.format(options.csv_file))

    z.stop()
    try:
        z.dump_scan_cache()
    except PermissionError as e:
        pass




def parse_target_args(targets):
    '''
    takes 
    '''

    networks = set()

    for network_list in targets:
        for network in network_list:
            networks.add(network)

    networks = sorted(networks)
    return networks







if __name__ == '__main__':

    default_bandwidth = '500K'
    default_work_dir = Path.home() / '.asset_inventory'
    default_cidr_mask = 16
    default_networks = [[ipaddress.ip_network(n)] for n in ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']]

    parser = argparse.ArgumentParser(description="Assess the security posture of an internal network")
    parser.add_argument('-t', '--targets', type=str_to_network, nargs='+',      default=default_networks, help='target network(s) to scan', metavar='STR')
    parser.add_argument('-p', '--ports', nargs='+', type=int,                   help='port-scan online hosts')
    parser.add_argument('-n', '--no-dns',           action='store_true',        help='do not perform reverse DNS lookups')
    parser.add_argument('--force-dns',              action='store_true',        help='force dns lookups while loading cache')
    parser.add_argument(
        '-B',
        '--bandwidth',
        default=default_bandwidth,
        help=f'max egress bandwidth (default {default_bandwidth})',
        metavar='STR',
    )

    parser.add_argument('-i', '--interface',                                    help='interface from which to scan (e.g. eth0)', metavar='IFC')
    parser.add_argument('-G', '--gateway-mac',                                  help='MAC address of default gateway', metavar='MAC')
    parser.add_argument('--blacklist',                                          help='a file containing hosts to exclude from scanning', metavar='FILE')
    parser.add_argument('--whitelist',                                          help='only these hosts (those which overlap with targets) will be scanned', metavar='FILE')
    parser.add_argument('-w', '--csv-file',                                     help='output CSV file', metavar='CSV_FILE')
    parser.add_argument('-f', '--start-fresh',      action='store_true',        help='discard cached data (a backup is made)')
    parser.add_argument('-Pn', '--skip-ping',       action='store_true',        help='skip zmap host-discovery')
    parser.add_argument('--force-ping',             action='store_true',        help='force a new zmap ping sweep')
    parser.add_argument('--force-syn',              action='store_true',        help='SYN scan hosts which have already been scanned')
    parser.add_argument(
        '-M',
        '--modules',
        nargs='*',
        default=[],
        help=f"Module for additional checks such as EternalBlue (pick from {', '.join(detected_modules + ['all', '*'])})",
    )

    parser.add_argument(
        '--work-dir',
        type=Path,
        default=default_work_dir,
        help=f'custom working directory (default {default_work_dir})',
        metavar='DIR',
    )

    parser.add_argument('-d', '--diff',             type=Path,                  help='show differences between scan results and IPs/networks from file', metavar='FILE')
    parser.add_argument(
        '--netmask',
        type=int,
        default=default_cidr_mask,
        help=f'summarize networks with this CIDR mask (default {default_cidr_mask})',
    )

    parser.add_argument('--make-deliverable',       action='store_true',        help='combine all data gathered for each host into a deliverable CSV file')

    try:

        options = parser.parse_args()
        options.targets = parse_target_args(options.targets)

        # make sure we have valid targets
        assert options.targets, 'No valid targets'
        # make sure ports are specified if there's no ping sweep
        assert (
            not options.skip_ping or options.ports
        ), 'Please specify port(s) to scan with -p'

        # make sure there's no conflicting options
        assert not (options.skip_ping and options.force_ping), 'Conflicting options: --force-ping and --skip-ping'

        assert 0 <= options.netmask <= 32, 'Invalid netmask'

        valid_module_chars = f'{string.ascii_lowercase}-'
        options.modules = [''.join([c for c in module.lower() if c in valid_module_chars]) for module in options.modules]
        if any(x in options.modules for x in ['all', '*']):
            options.modules = detected_modules
        elif any(module not in detected_modules for module in options.modules):
            raise AssertionError(
                f"Invalid module name, please pick from the following: {', '.join(detected_modules)}"
            )


        main(options)


    except (argparse.ArgumentError, AssertionError) as e:
        sys.stderr.write(f'\n[!] {str(e)}\n\n')
        sys.exit(2)

    except KeyboardInterrupt:
        sys.stderr.write('\n[!] Interrupted\n')
        sys.exit(1)