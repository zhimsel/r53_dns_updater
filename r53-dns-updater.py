#!/usr/bin/env python3
"""r53-dns-updater

Gets the public IP address of the host and updates a given Route53 record

This script assumes your AWS credentials are in the one of the locations that
boto3 searches. For more information on setting up your credentials, see:
http://boto3.readthedocs.io/en/latest/guide/configuration.html

Usage:
    r53-dns-updater --help
    r53-dns-updater [options] <target_record>

Options:
    --help, -h          Display this message
    --verbose, -v       Show extra logging info

To protect incorrect configurations or accidental typos, this script will not
overwrite any records that do not match the expected A-record type.
"""
from docopt import docopt
import logging
import logging.handlers
import boto3
import sys
import ipgetter

# Set up global logging object
log = logging.getLogger(__name__)
log.propagate = False


class DynamicDnsRecord(object):
    """
    Class to manage a Dynamic DNS record that needs to be kept up-to-date
    """

    def __init__(self, target_record):
        """
        Args:
            target_record (str): the DNS record to update
        """
        assert isinstance(target_record, str)

        # Init some core class objects
        self._r53_api = boto3.client('route53')
        self.target_record = target_record

        # Init lazy-load properties
        self._r53_hosted_zones = None  # dict()
        self._domain_name = None  # str()

        self.hosted_zone = self.r53_hosted_zones[self.domain_name]
        self.actual_ip = ipgetter.myip()

    @property
    def r53_hosted_zones(self):
        """
        Return a dict of all our hosted zones and their IDs

        Returns:
            dict: {zone_name: zone_id, ...}
        """
        if self._r53_hosted_zones is None:
            self._r53_hosted_zones = dict()

            # For each hosted zone...
            for zone in self._r53_api.list_hosted_zones_by_name(
                    MaxItems='100')['HostedZones']:
                # Cut off the trailing '.'
                zone_name = '.'.join(zone['Name'].split('.')[:-1])
                # Get just the ID, not the full path
                zone_id = zone['Id'].split('/')[-1:][0]
                # Add to our dict
                self._r53_hosted_zones[zone_name] = zone_id

        return self._r53_hosted_zones

    @property
    def domain_name(self):
        """
        Using the list of hosted zones, programatically determine what the
        domain name for the given DNS record is

        Returns:
            str
        """
        if self._domain_name is None:

            # Get a simple list of valid domain names from our hosted zones
            valid_domains = list(
                zone.split('.') for zone in self.r53_hosted_zones.keys())

            # Split the hostname string into domain parts. For each part,
            # if it's in the list of valid domains, then we have determined our
            # domain. If it's not, remove the first part, and try again.
            domain = self.target_record.split('.')
            while True:
                if domain in valid_domains:
                    break
                else:
                    try:  # If we have no more parts, `del` will fail
                        del domain[0]
                    except IndexError:
                        log.critical('DNS record \'%s\' does not belong ' +
                                     'to a valid Route53 hosted zone in ' +
                                     'the given AWS account!',
                                     self.target_record)
                        sys.exit(1)
            self._domain_name = '.'.join(domain)

        return self._domain_name


def main():
    """Main program"""

    # Init docopt arguments
    args = docopt(__doc__, help=True)

    # Determine loglevel
    if args['--verbose']:
        log_level = 'INFO'
    else:  # default to ERROR if no override is given
        log_level = 'ERROR'
    log_level_num = getattr(logging, log_level.upper(), None)
    if not isinstance(log_level_num, int):
        raise ValueError('Invalid log level: {}'.format(log_level))
    log.setLevel(log_level_num)
    logging.basicConfig(level=log_level_num)

    # Set up console logger
    log_console = logging.StreamHandler()
    log_console.setLevel(logging.DEBUG)
    log_console.setFormatter(logging.Formatter(
        fmt='%(levelname)s:%(message)s',
        datefmt='%Y/%m/%d %H:%M:%S %Z'))
    log.addHandler(log_console)

    # Init our class object
    dns_record = DynamicDnsRecord(args['<target_record>'])

if __name__ == "__main__":
    main()
