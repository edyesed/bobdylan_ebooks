""" This module responds to notifications by polling the twitter api for notifications

It responds to both regular tweet and DM events, and responds to each in kind.

"""
from __future__ import print_function
import sys
import os
import json
import re
import random
from datetime import datetime
import boto3
# load vendored directory
sys.path.append(os.path.join(here, "./vendored"))
import pymarkovchain #pylint: disable=C0413
import twitter #pylint: disable=C0413
# Import regular_tweet, included in this package
import regular_tweet #pylint: disable=C0413

TWITTER_CONSUMERKEY = os.environ.get('TWITTER_CONSUMERKEY', None)
TWITTER_SECRET = os.environ.get('TWITTER_SECRET')
TWITTER_ACCESS_TOKEN = os.environ.get('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_TOKEN_SECRET = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
TWITTER_OWNER_ID = os.environ.get('TWITTER_OWNER_ID')
DYNAMO = boto3.resource('dynamodb')
SONGS_TABLE = DYNAMO.get_table(os.environ.get('DYNAMO_SONGS', None))
EVENTS_TABLE = DYNAMO.get_table(os.environ.get('DYNAMO_EVENTS', None))


# Search the Dynamo Table
# return a random set of 40
#
def song_search(limit=40):
    """Search the DynamoDB Table of songs, randomly return
       $limit songs"""
    all_songs = SONGS_TABLE.scan()
    return random.sample(all_songs, limit)


def print_with_timestamp(*args):
    """
       Default printer is print
    """
    print(datetime.utcnow().isoformat(), *args)


def markov_response(songs=None, max_len=140, reply_handle=None):
    """Make the text of the response
    """
    if reply_handle:
        response_text = "@{0} ".format(reply_handle)
    markovchain = pymarkovchain.MarkovChain()
    for song in songs:
        #print("training with text: %s" % (songwords['_source']['text']))
        markovchain.generateDatabase(song['songinfo']['text'], sentenceSep='\r\n')
    # concat four markovs together
    response_text += markovchain.generateString()
    response_text += "\n" + markovchain.generateString()
    response_text += "\n" + markovchain.generateString()
    response_text += "\n" + markovchain.generateString()
    keepwords = regular_tweet.trim_to_140(text=response_text)

    try:
        response_text = keepwords.lowercase()
    except:
        response_text = keepwords
    print("ACTUAL RESPONSE: %s:  %s" % (len(response_text),
                                        json.dumps(response_text)))
    return(response_text)


def twitter_reply(reply_type="", reply_text="", reply_handle=None, tweet_id=None):
    api = twitter.Api(consumer_key=TWITTER_CONSUMERKEY,
                      consumer_secret=TWITTER_SECRET,
                      access_token_key=TWITTER_ACCESS_TOKEN,
                      access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)
    if reply_type == "TWEET":
        print("TWEET ID I'M RESPONDING TO")
        print(tweet_id)
        response = api.PostUpdate(
            reply_text, in_reply_to_status_id=tweet_id)
        #response = api.PostUpdate(reply_text, in_reply_to_status_id=tweet_id)
        print("twitter response")
        print(response)
    if reply_type == "DM":
        print("DM HANDLE I'M RESPONDING TO")
        print(reply_handle)
        response = api.PostDirectMessage(
            screen_name=reply_handle, text=reply_text)
        print("twitter response")
        print(response)
    pass


def respond(event, context):
    """ 
        Now we're invoked on a schedule, and using the twitter api to 
          get notifications, and respond
    """
    try:
        api = twitter.Api(consumer_key=TWITTER_CONSUMERKEY,
                          consumer_secret=TWITTER_SECRET,
                          access_token_key=TWITTER_ACCESS_TOKEN,
                          access_token_secret=TWITTER_ACCESS_TOKEN_SECRET)
    except Exception as e:
        print_with_timestamp("Failed to connect to twitter api: {0}".format(e))

    # Query, find the highest notification id
    # 
    mentions = False
    max_id = False
    ### XXX
    ### XXX
    # OK COME IN HERE AND GET UNRESPONDED THINGS OUT OF DYNAMO
    ### XXX
    ### XXX
    try:
        res = es.search(index='mentions', 
                        doc_type='bobdylan_ebooks', 
                        body={"query": {"match_all": {}}, 
                              "sort": [{"id": "desc"}]
                             },
                        filter_path=['hits.total','hits.hits._source.id'])
        if len(res['hits']['hits']) > 0:
            # stuff was in elasticsearch, start from highest id
            max_id = res['hits']['hits'][0]['_source']['id']
            print("Max id of notification from ES was {0}".format(max_id))
        else:
            print_with_timestamp("Nothing in elasticsearch")
            # get 10 mentions from twitter
    except elasticsearch.exceptions.NotFoundError:
        # 
        # index does not exist, get mentions and create it
        # 
        mentions = api.GetMentions(count=10)
        for mention in mentions:
             es.index(index='mentions',
                      doc_type='bobdylan_ebooks',
                      id=mention.AsDict()['id'],
                      body=mention.AsDict())
    
    if mentions is False:
        if max_id is not False:
            # get up to 25 mentions since the last gotten mention
            mentions = api.GetMentions(since_id=max_id, count=25)
        else:
            print("NO IDEA. mentions was false, and no max_id")
            return False

    if len(mentions) is 0:
        print("There we no new mentions.")
        return True

    for mention in mentions:
        ## Find what they asked about, remove handles
        input_text = re.sub("\s+@\S+", "", mention.text)
        results = song_search()
        try:
            markov = markov_response(es_results=results, 
                                     reply_handle=mention.user.screen_name)
        except Exception as e:
            raise Exception("Failed response building as exception %s" % (e))
        print("DOING TWITTER REPLY")
        print(json.dumps(
                  "reply_id:{0} handle:{1} len:{2} text:{3}".format(
                      mention.id,
                      mention.user.screen_name,
                      len(markov),
                      markov)))
        twitter_reply(reply_type="TWEET",
                      reply_text=markov,
                      reply_handle="@" + mention.user.screen_name,
                      tweet_id=mention.id)
        es.index(index='mentions',
                 doc_type='bobdylan_ebooks',
                 id=mention.AsDict()['id'],
                 body=mention.AsDict())
    return True

