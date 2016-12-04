# bobdylan_ebooks
The code what runs [@bobdylan_ebooks](https://twitter.com/bobdylan_ebooks) twitter handle. 

[@bobdylan_ebooks](https://twitter.com/bobdylan_ebooks) tweets [markov chains](https://pypi.python.org/pypi/PyMarkovChain/) built from the lyrics of *The Songs of Bob Dylan*

# How it works
There components, three.

1. A batch job that imports song data
2. A Lambda attached to SNS ( which is attached to SES ) responds to tweets by way of email. 
3. A Lambda with a batch schedule regularly tweets things

## The Batch Job That Imports Song Data
[bin/find-and-download-songs.py](bin/find-and-download-songs.py) scans [http://bobdylan.com/songs](http://bobdylan.com/songs), and iterates over the songs listed there. 

As it iterates through the list, it adds entries to elasticsearch

1. A Song list originates from loading [bob's songs](http://bobdylan.com/songs/).
1. Each song listed there is requested.
1. *NEW FEATURE*: a `tags` field is added to the documents by way of [AutoTag](https://algorithmia.com/algorithms/nlp/AutoTag) from [algorithmia](https://algorithmia.com)
1. The text is inserted into elasticsearch


## The lambda that is attached to SNS ( which is attached to an email address via SES ) 
Twitter will send you an email ( most of the time ), when somebody tweets at you. 

If one were willing to parse that email, you might be able to extract the text, and formulate a response.

1. Email comes into SES
1. SES is configured to route an email address to a SNS topic
1. The SNS Topic is configured to deliver to a lambda.
1. The lambda:
      1. Parses the email
      1. Extracts the originating twitter handle
      1. Extracts the text sent in the tweet
      1. Searches elasticsearch for that text
           1. **FUTURE FEATURE**: it should look against the tags to match
      1. Builds a markov based response based out of the search results
      1. Responds to the originating handle via the twitter API

## The lambda that runs on a batch schedule
This lambda is what regularly posts to the bobdylan_ebooks timeline

1. The lambda inits
1. Queries all songs in elasticsearch
     1. searches for '*'
     1. Randomizes the results
1. makes markov chains from the results
