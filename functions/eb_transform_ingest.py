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
Transform partner event recieved from EventBrdige and ingest in to CloudTrail Lake
Current Version: 1.0
Current Version supports only Okta Authentication events transformation and ingestion
'''

import json
import datetime
import logging
import os
import sys
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setLevel(logging.DEBUG)
LOGGER.addHandler(HANDLER)
VERSION = boto3.__version__

CHANNEL_ARN = os.environ['CHANNEL_ARN']
REGION = CHANNEL_ARN.split(':')[3]
SESSION = boto3.session.Session(region_name=REGION)
STS = SESSION.client('sts')
R_ID=STS.get_caller_identity()['Account']


def transform_event(record):
    '''
    Transform Partner event in to CloudTrail acceptable Schema.
    returns transformed event
    '''

    e_d = {}
    e_d['version'] = record['version']
    e_d['UID'] = record['id']
    detailer = record['detail']
    o_actor = detailer['actor']
    user_idnty = {}
    user_idnty['type'] =  o_actor['type']
    user_idnty['principalId'] =  o_actor['id']
    user_idnty['details'] =  {"alternateId": o_actor['alternateId'],
                                "displayName": o_actor['displayName']}
    e_d['userIdentity'] = user_idnty
    date_obj=datetime.datetime.strptime(detailer['published'], '%Y-%m-%dT%H:%M:%S.%fZ')
    ct_date=str(date_obj.date())+'T'+str(date_obj.time()).rsplit('.', maxsplit=1)[0]+'Z'
    e_d['eventTime'] = ct_date
    e_d['eventName'] =detailer['debugContext']['debugData']['requestUri']
    e_d['eventSource'] = "okta.system-log-events"
    e_d['additionalEventData'] = detailer
    e_d['sourceIPAddress'] = detailer['client']['ipAddress']
    e_d['recipientAccountId'] = record['account']

    outcome = detailer['outcome']
    e_d['responseElements'] = {"outcome.reason": outcome['result']}
    if outcome['result'] not in ['SUCCESS', 'ALLOW']:
        e_d['errorCode'] = outcome['result']
        if not outcome['reason']:
            e_d['errorMessage'] = "NULL"
        else:
            e_d['errorMessage'] = outcome['reason']

    event_data = json.dumps(e_d)
    audit_event = {"auditEvents": [{"eventData": event_data, "id": str(uuid4())}]}

    return audit_event

def ingest_event(t_event, channel_arn):
    '''
    Ingest an Audit event in to CloudTrail Event DataStore
    Return True: if successful, False: if not
    '''

    ct_oae = boto3.client('cloudtrail-data')
    result = True

    try:
        output = ct_oae.put_audit_events(auditEvents=t_event['auditEvents'],
                                         channelArn=channel_arn)
        failed = output['failed']
        if len(failed) == 0:
            LOGGER.info('Event successfully ingested: %s', output['successful'])
        else:
            raise Exception('Error to ingest event: ', failed)

    except ClientError as exe:
        raise Exception('Error to ingest event: ', str(exe)) from exe

    return result

def lambda_handler(event, context):
    """
    This is where Lambda starts the magic.
    """

    LOGGER.info("Context: %s", context)
    LOGGER.info("Version: %s", VERSION)

    for item in event['Records']:
        body = json.loads(item['body'])

        # Transform the ISSUE in to CloudTrail format
        result = transform_event(body)
        # Ingest the CloudTrail format event in to Lake
        ingest_event(result, CHANNEL_ARN)
