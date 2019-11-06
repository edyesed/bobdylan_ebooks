from __future__ import print_function
import sys
import os

# regular include stuff
import json
import datetime
import re
import elasticsearch
import pymarkovchain

from elasticsearch import RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from twilio import twiml
from urlparse import parse_qs
#import twitter

#from pprint import pprint
#from datetime import datetime


def endpoint(event, context):
    resp = twiml.Response()
    print(json.dumps(event))
    ### the incoming request(event) has a field called 'body' where the relevant
    ### info appears formatted as a querystring 
    try:
        parsed_body = parse_qs(event['body'])
    except AttributeError:
        # due to $reasons, this comes in as a dict.
        parsed_body = event['body']
    ### Inside the parsed body, the inbound text is in a field called Body
    sent_words = parsed_body['Body'][0]
    print(json.dumps(parsed_body))

    resp.message("Hello there. {0}".format(sent_words))
    return str(resp)
