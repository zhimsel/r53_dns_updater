#!/usr/bin/env python3
"""r53_dns_updater

Gets the public IP address of the host and updates a given Route53 record

This script assumes your AWS credentials are in the one of the locations that
boto3 searches. For more information on setting up your credentials, see:
http://boto3.readthedocs.io/en/latest/guide/configuration.html

Usage:
    r53_dns_updater --help
    r53_dns_updater [options] <target_record>

Options:
    --help, -h            Display this message
    --verbose, -v         Show extra logging info
    --ttl TTL, -t TTL     Override existing and/or default TTL
    --sns SNS_TOPIC_ARN   Optional SNS topic ARN to notify on record updates

To protect incorrect configurations or accidental typos, r53_dns_updater won't
overwrite any records that:
    - isn't already an 'A' record
    - has more than one target IP (i.e. round-robin)

If the target record already exists, the existing TTL value will be used.
If the target record does not exist, a TTL of 60 seconds will be used.
You can override this with the --ttl option (existing TTL will be ignored).
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


class InvalidRecordTargetError(Exception):
    """
    Exception to be raised if the targets for a ResourceRecordSet is not
    what we expect it to be.
    """


class DynamicDnsRecord(object):
    """
    Class to manage a Dynamic DNS record that needs to be kept up-to-date
    """

    def __init__(self, target_record, sns_arn=None):
        """
        Args:
            target_record (str): The DNS record to update
            sns_arn (str): Optional SNS topic to notify on record changes
        """
        if not isinstance(target_record, str):
            raise TypeError(
                "DynamicDnsRecord(): 'target_record' must be a string")

        # Init some core class objects
        self._r53_api = boto3.client('route53')
        self.target_record = target_record
        self.sns_arn = sns_arn

        # Init lazy-load properties
        self._r53_hosted_zones = None  # dict()
        self._domain_name = None  # str()

        self.hosted_zone = self.r53_hosted_zones[self.domain_name]
        self.actual_ip = ipgetter.myip()
        self.current_ip, self.current_ttl = self.get_current_record()

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
            log.info('Determined the target record \'%s\' belongs to ' +
                     'the hosted zone \'%s\' (%s)',
                     self.target_record, self._domain_name,
                     self.r53_hosted_zones[self._domain_name])

        return self._domain_name

    def get_current_record(self):
        """
        Return existing IP and TTL of the target record (as reported by R53)
        If a matching record does not exist, return None for both.

        Returns:
            tuple: ip_address (str or None), ttl (str or None)
        """
        # Get a list of records from our target record's hosted zone.
        # We might get a truncated list, so loop until we have them all
        record_sets = list()
        start_record_name = self.target_record  # might as well start here
        start_record_type = 'A'  # start with A-records; that's what we want
        while True:

            # Get a batch of 100 records for the hosted zone, starting with
            # our record name and type (this will reduce the unnecessary
            # records given back)
            response = self._r53_api.list_resource_record_sets(
                HostedZoneId=self.hosted_zone,
                MaxItems='3',
                StartRecordName=start_record_name,
                StartRecordType=start_record_type)

            # Add the batch's record list to ours
            record_sets.extend(response['ResourceRecordSets'])

            # If the batch is truncated, we'll have to loop again
            if response['IsTruncated'] is True:
                log.debug('R53 API record set list response was truncated')
                start_record_name = response['NextRecordName']
                start_record_type = response['NextRecordType']
            else:
                break

        # Now that we have our complete list of records, find ours
        our_record_targets = list()
        our_record_ttl = None
        for record in record_sets:
            # Remove the trailing '.'
            if '.'.join(record['Name'].split('.')[:-1]) == self.target_record:
                # Only match A records
                if record['Type'] == 'A':
                    our_record_targets = record['ResourceRecords']
                    our_record_ttl = str(record['TTL'])

        # Validate our record targets agains expected values
        if len(our_record_targets) > 1:
            msg = ('Error: It appears the specified record \'{}\' has ' +
                   'more than one target! Are you sure you specified the ' +
                   'correct record? If so, please manually remove the ' +
                   'targets (or leave just one).').format(self.target_record)
            raise InvalidRecordTargetError(msg)
        elif len(our_record_targets) < 1:
            log.info('Target record seems to not exist')
            return None, our_record_ttl
        else:
            log.info('Existing record found with target of %s and TTL of %s',
                     our_record_targets[0]['Value'], our_record_ttl)
            return our_record_targets[0]['Value'], our_record_ttl

    def publish_to_sns(self, msg):
        """
        Attempt to publish a message to the provided SNS topic

        Args:
            msg (str): body for the SNS message
        """
        if not isinstance(msg, str):
            raise TypeError("publish_to_sns(): 'msg' must be a string")

        if isinstance(self.sns_arn, type(None)):
            raise ValueError(
                "publish_to_sns(): trying to publish to an SNS topic, "
                "but 'sns_arn' was not provided")

        # Determine which region we need to use, because the 'default' region
        # (as set by config) needs to match the region of the SNS topic
        aws_region = self.sns_arn.split(':')[3]
        sns = boto3.client('sns', region_name=aws_region)

        try:
            sns.publish(TopicArn=self.sns_arn, Message=msg)
        except Exception as e:
            log.error('Failed to send SNS message: %s', e)

    def update_target_record_value(self, ttl=None):
        """
        Check if the current value of the record differs from our actual public
        IP address and update the record in R53 if it does

        Args:
            ttl (str): optional TTL to specify for the target
        """
        if not isinstance(ttl, (str, type(None))):
            raise TypeError(
                "update_target_record_value(): 'ttl' must be a string")

        # If the user specified a TTL override, use that. Otherwise, use the
        # existing target record's TTL. If the target record doesn't exist,
        # use a sane default of 60.
        if ttl is None:
            if self.current_ttl is not None:
                ttl = self.current_ttl
                log.info('Using existing TTL value of %s', ttl)
            else:
                ttl = '60'
                log.info('No existing record found, using default TTL of %s',
                         ttl)
        else:
            log.info('Overriding TTL with provided value of %s', ttl)

        # Only make the change if the IP is actually different
        if self.actual_ip != self.current_ip:
            log.warning('Updating out-of-date DNS record \'%s\' ' +
                        'to point to %s (previous target: %s)',
                        self.target_record,
                        self.actual_ip,
                        self.current_ip)

            # Construct the changebatch to be sent to Route53
            changebatch = {'Changes': [
                {'Action': 'UPSERT',
                 'ResourceRecordSet': {
                     'Name': self.target_record,
                     'Type': 'A',
                     'TTL': int(ttl),
                     'ResourceRecords': [{'Value': self.actual_ip}]
                 }}]}

            # Send the change request to the Route53 API
            self._r53_api.change_resource_record_sets(
                HostedZoneId=self.hosted_zone,
                ChangeBatch=changebatch)

            # If requested, send an SNS message to alert that the IP changed
            if self.sns_arn:
                self.publish_to_sns(
                    'IP for DNS record {} changed to {}'.format(
                        self.target_record, self.actual_ip))

        else:
            log.info('Target DNS record is already up-to-date, nothing to do')


def main():
    """Main program"""

    # Init docopt arguments
    args = docopt(__doc__, help=True)

    # Determine loglevel
    if args['--verbose']:
        log_level = 'INFO'
    else:  # default to ERROR if no override is given
        log_level = 'WARNING'
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
    dns_record = DynamicDnsRecord(args['<target_record>'],
                                  args['--sns'])

    # Update the DNS record if it's out-of-date
    dns_record.update_target_record_value(ttl=args['--ttl'])


if __name__ == "__main__":
    main()