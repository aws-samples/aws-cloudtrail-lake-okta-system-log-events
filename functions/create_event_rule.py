#
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify,merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
#
'''
Create Event Rule on partner event bus.
The current cloudformation resource AWS::Events::Rule do not support
creating event rule on partner event bus.
The CloudFormation resource fails with below error:
EventBus name starting with 'aws.' is not valid.
'''

import json
import logging
import sys
import os

import boto3
from botocore.exceptions import ClientError

import cfnresource

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setLevel(logging.DEBUG)
LOGGER.addHandler(HANDLER)
VERSION = boto3.__version__
EVENT = boto3.client('events')


def create_event_rule(rule_name, bus_name, event_pattern,
                      description='Created by CloudFormation'):
    '''
    Create Event Rule on partner event bus
    '''

    result = True
    try:
        response = EVENT.put_rule(
            Name=rule_name,
            EventPattern=event_pattern,
            State='ENABLED',
            Description=description,
            EventBusName=bus_name
        )
        LOGGER.info('Event Rule created: %s', response)
    except ClientError as exe:
        LOGGER.error("FAILED to create event rule: %s", str(exe))
        result = False

    return result


def create_event_target(rule_name, target, bus_name):
    '''
    Add event target to event rule
    '''

    result = True

    try:
        response = EVENT.put_targets(
            Rule=rule_name,
            Targets=target,
            EventBusName=bus_name
        )
        LOGGER.info('Event Target created: %s', response)
    except ClientError as exe:
        LOGGER.error("FAILED to create event target: %s", str(exe))
        result = False

    return result


def get_associated_targets(rule_name, bus_name):
    '''
    Get event targets associated with event rule
    '''

    result = []
    try:
        response = EVENT.list_targets_by_rule(
            Rule=rule_name,
            EventBusName=bus_name
        )
        LOGGER.info('Event Targets associated with rule: %s', response)
        for item in response['Targets']:
            result.append(item['Id'])
    except ClientError as exe:
        LOGGER.error("FAILED to get associated targets: %s", str(exe))

    return result


def remove_targets(rule_name, bus_name):
    '''
    Delete Event rule
    '''

    result = True
    target_list = get_associated_targets(rule_name, bus_name)

    try:
        if target_list:
            response = EVENT.remove_targets(
                Rule=rule_name,
                Ids=target_list,
                EventBusName=bus_name
            )
            LOGGER.info('Event Targets removed: %s', response)
    except ClientError as exe:
        LOGGER.error("FAILED to delete event target: %s", str(exe))
        result = False

    return result


def delete_event_rule(rule_name, bus_name):
    '''
    Delete Event rule
    '''

    result = True

    remove_targets(rule_name, bus_name)

    try:
        response = EVENT.delete_rule(
            Name=rule_name,
            EventBusName=bus_name
        )
        LOGGER.info('Event Rule deleted: %s', response)
    except ClientError as exe:
        LOGGER.error("FAILED to delete event rule: %s", str(exe))
        result = False

    return result


def lambda_handler(event, context):
    '''Lambda Handler'''

    output = list()
    rule_name = os.environ['RULE_NAME']
    bus_name = os.environ['EVENT_BUS_NAME']
    prefix = "/".join(bus_name.split('/')[0:2])
    pattern = {"source": [{"prefix": prefix}]}
    rule_target = [{"Id": "PartnerOAE_Queue",
                    "Arn":  os.environ['TARGET_ARN']
                    }]

    request_type = event['RequestType']
    LOGGER.info('VERISON: %s', VERSION)
    LOGGER.info('Request Recieved: %s', request_type)

    if request_type in ['Create', 'Update']:
        if request_type == 'Update':
            output.append(delete_event_rule(rule_name, bus_name))

        output.append(create_event_rule(rule_name, bus_name,
                                        json.dumps(pattern),
                                        description='Process partner events'))
        output.append(create_event_target(rule_name, rule_target, bus_name))
    elif request_type == 'Delete':
        output.append(delete_event_rule(rule_name, bus_name))
    else:
        LOGGER.error('Unknown Request Type: %s', request_type)
        output.append(cfnresource.SUCCESS)

    LOGGER.info('OUTPUT: %s', output)

    if False not in output:
        response = {}
        cfnresource.send(event, context, cfnresource.SUCCESS,
                         response, "CustomResourcePhysicalID")
    else:
        response = {"error": "Failed to load the data"}
        LOGGER.error(output)
        cfnresource.send(event, context, cfnresource.FAILED,
                         response, "CustomResourcePhysicalID")
