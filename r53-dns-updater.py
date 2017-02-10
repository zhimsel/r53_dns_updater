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

# Set up global logging object
log = logging.getLogger(__name__)
log.propagate = False


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


if __name__ == "__main__":
    main()
