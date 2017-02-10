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


def main():
    """Main program"""

    # Init docopt arguments
    args = docopt(__doc__, help=True)


if __name__ == "__main__":
    main()
