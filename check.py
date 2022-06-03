#!/usr/bin/env python3
#
# Copyright (C) 2015 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import json
import signal
import sys
import shutil
import subprocess
import jsonschema
import argparse
from picture import get_size

APPLIANCE_IDS = []
SCHEMA_VERSIONS = [3, 4, 5, 6]

warnings = 0


def no_additional_properties(schema):
    if 'items' in schema:
        schema = schema['items']
    if 'properties' in schema:
        if 'additionalProperties' not in schema:
            schema['additionalProperties'] = False
        for key in schema['properties']:
            if isinstance(schema['properties'][key], dict):
                no_additional_properties(schema['properties'][key])


def validate_schema(appliance_json, name, schemas):
    global warnings

    version = appliance_json['registry_version']
    if version not in SCHEMA_VERSIONS:
        print('Schema version {} is not supported'.format(version))
        sys.exit(1)

    jsonschema.validate(appliance_json, schemas[version])

    if version != SCHEMA_VERSIONS[0]:
        try:
            version -= 1
            appliance_json = appliance_json.copy()
            appliance_json['registry_version'] = version
            jsonschema.validate(appliance_json, schemas[version])
            print('Appliance {name} can be downgraded to registry version {version}'.format(name=name, version=version))
            warnings += 1
        except jsonschema.exceptions.ValidationError:
            pass


def signal_abort(sig, frame):
    print('\n\n=> Check aborted\n')
    sys.exit(0)


def check_appliance(appliance, appliance_path='appliances'):
    global warnings
    images = {}
    md5sums = set()

    schemas = {}
    for version in SCHEMA_VERSIONS:
        schema_filename = "schemas/appliance_v{}.json".format(version)
        with open(schema_filename) as f:
            schemas[version] = json.load(f)
            no_additional_properties(schemas[version])

    with open(os.path.join(appliance_path, appliance)) as f:
        appliance_json = json.load(f)

    validate_schema(appliance_json, appliance, schemas)

    appliance_id = appliance_json.get("appliance_id")
    if appliance_id in APPLIANCE_IDS:
        print('Duplicate appliance UUID detected ' + appliance_id)
        sys.exit(1)
    APPLIANCE_IDS.append(appliance_id)

    if 'images' in appliance_json:
        for image in appliance_json['images']:
            if image['filename'] in images:
                print('Duplicate image filename ' + image['filename'])
                sys.exit(1)
            if image['md5sum'] in md5sums:
                print('Duplicate image md5sum ' + image['md5sum'])
                sys.exit(1)
            versions_found = False
            for version in appliance_json['versions']:
                if image['filename'] in version['images'].values():
                    versions_found = True
            if not versions_found:
                print('Unused image ' + image['filename'] + ' in ' + appliance)
                warnings += 1
            images[image['filename']] = image['version']
            md5sums.add(image['md5sum'])

        for version in appliance_json['versions']:
            version_match = False
            for image in version['images'].values():
                if image not in images:
                    print('Missing relation ' + image + ' in ' + appliance + ' for version ' + version['name'])
                    sys.exit(1)
                if images[image] == version['name']:
                    version_match = True
            if not version_match:
                print('Version mismatch for version ' + version['name'] + ' in ' + appliance)
                sys.exit(1)


def check_packer(packer, packer_path='packer'):
    path = os.path.join(packer_path, packer)
    if not os.path.isdir(path):
        return
    for file in os.listdir(path):
        if file.endswith('.json'):
            print('Check {}/{}'.format(packer, file))
            with open(os.path.join('packer', packer, file)) as f:
                json.load(f)


def image_get_height(filename):
    with open(filename, 'rb') as image_file:
        image_data = image_file.read()
        width, height, filetype = get_size(image_data)
    return height


use_imagemagick = shutil.which("identify")


def check_symbol(symbol, symbols_path='symbols'):
    licence_file = os.path.join(symbols_path, symbol.replace('.svg', '.txt'))
    if not os.path.exists(licence_file):
        print("Missing licence {} for {}".format(licence_file, symbol))
        sys.exit(1)
    if use_imagemagick:
        height = int(subprocess.check_output(['identify', '-format', '%h', os.path.join(symbols_path, symbol)], shell=False))
    else:
        height = image_get_height(os.path.join(symbols_path, symbol))
    if height > 70:
        print("Symbol height of {} is too big {} > 70".format(symbol, height))
        sys.exit(1)


def main():
    global warnings
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--appliance-dir', type=str, default='appliances', help="directory to search for appliances")
    parser.add_argument('-p', '--packer-dir', type=str, default='packer', help="check packer files in given directory")
    parser.add_argument('-s', '--symbols-dir', type=str, default='symbols', help="check symbol images in given directory")


    args = parser.parse_args()

    signal.signal(signal.SIGINT, signal_abort)
    print("=> Check appliances")
    for appliance in os.listdir(args.appliance_dir):
        if appliance.endswith('.gns3a'):
            print('Check {}'.format(appliance))
            check_appliance(appliance, args.appliance_dir)
    print("=> Check symbols")
    for symbol in os.listdir(args.symbols_dir):
        if symbol.endswith('.svg'):
            print('Check {}'.format(symbol))
            check_symbol(symbol)
    print("=> Check packer files")
    for packer in os.listdir(args.packer_dir):
        check_packer(packer)
    if warnings:
        print("{} warning!".format(warnings))
    else:
        print("Everything is ok!")


if __name__ == '__main__':
    main()
