#!/usr/bin/env python
"""Now  a vestigial tail
"""
## Makes the table locally
import os
import boto3


DB_URL = os.environ.get('DYNAMODB_URL', 'http://localhost:8000')
dynamodb = boto3.client('dynamodb', endpoint_url=DB_URL)

table = dynamodb.create_table(
            TableName='bobdylan_songs',
            KeySchema=[{'AttributeName': 'title', 'KeyType': 'HASH'},
                       {'AttributeName': 'id', 'KeyType': 'RANGE'} ],
            AttributeDefinitions=[
                       {'AttributeName': 'title', 'AttributeType': 'S'},
                       {'AttributeName': 'id', 'AttributeType': 'S' }],
            ProvisionedThroughput={'ReadCapacityUnits': 10,
                                   'WriteCapacityUnits': 10}
        )

