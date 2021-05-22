import io
import simplejson as json
import praw
import re
import time

from random import choice
from prawcore.exceptions import PrawcoreException as APIException # PRAW API exception handlers

class ReplyBot:

  def __init__(self):
    with open('settings/config.json') as config_file:
      config = json.load(config_file)
      self.SITE_NAME = config['SITE_NAME']
      self.USER_NAME = config['USER_NAME']

    with open('settings/environment.txt') as environment_file:
      self.environment = environment_file.read().strip()

    self.reddit = praw.Reddit(site_name=self.SITE_NAME) # site name defines reddit variables from praw.ini
    with open('settings/subreddits.json') as subreddits_file:
      subs = json.load(subreddits_file)[self.environment]
      self.subreddits = '+'.join([sub['name'] for sub in subs]) # get '+'-separated list of subreddits
                                                                # e.g '/r/WOT+wetlanderhumor'
      self.subreddits_w_flairs = subs

    with io.open('data/quotes.json', mode='r', encoding='utf-8') as quotes_file:
      self.quotes = json.load(quotes_file)  # create a list of all quotes
      self.keywords = sum([
        trigger['triggers'] for trigger in self.quotes ],
        []
      ) # create the list of keywords to listen for in comments

    with open('data/answered') as answered_file:
      self.answered_comments = answered_file.read().split('\n') # don't reply to the same comment more than once

    with open('data/blocked_users') as blocked_file:
      self.blocked_users = blocked_file.read().split('\n') # don't reply to users who don't want replies

  def log(self, string):
    if self.environment == 'PRODUCTION':
      with open('data/log.txt', 'a') as log_file:
        log_file.write(string + '\n')
    else:
      print(string)

  def register_reply(self, comment_id):
    self.answered_comments.append(comment_id)
    with open('data/answered', 'a') as answered_file: # log successful reply so we
      answered_file.write(comment_id + '\n')          # don't reply again

  def get_legal_quote(self, comment):
    for character in self.quotes:
      if any([trigger in comment for trigger in character['triggers']]):
        quotes = character['quotes']
        break
    return choice(quotes)

  def get_comment_from_id(self, id):
    return self.reddit.comment(id)

  def block_user(self, user):
    self.blocked_users.append(user)
    with open('data/blocked_users', mode='a') as blocked_file:
      blocked_file.write(user)

  def get_intent(self, comment):
    author = comment.author.name.lower()
    sub = next(x for x in self.subreddits_w_flairs if x['name'] == comment.subreddit.display_name)
    if (
        author == self.USER_NAME or
        author in self.blocked_users or
        comment.id in self.answered_comments or (
        comment.submission.link_flair_text is not None and
        comment.submission.link_flair_text.lower() in sub['flair-blacklist']
        )
      ):
      return False
    if ( 
      comment.parent().author is not None and
      comment.parent().author.name.lower() == self.USER_NAME and
      comment.body.lower().find('!stop') == 0
      ):
      return 'block'
    if (any(re.search(keyword, comment.body, re.IGNORECASE) for keyword in self.keywords) and 
        ( len(sub['flair-whitelist']) == 0 or
        comment.submission.link_flair_text is None or
        comment.submission.link_flair_text.lower() in sub['flair-whitelist']
        )):
      return 'reply'

  def reply_bot(self):
    while True:
      self.log(f'\n\nRunning {self.SITE_NAME} on reddit.com/r/' + self.subreddits)
      try:
        for comment in self.reddit.subreddit(self.subreddits).stream.comments(): # continuous stream of comments
                                                                            # from chosen subreddits
          comment_text = comment.body
          comment_id = comment.id
          intent = self.get_intent(comment)
          if intent == 'block': # allow users to reply with 
            author = comment.author.name  # !stop to be blocked from replies
            self.log(f'blocking user {author}')
            self.block_user(author)
          elif intent == 'reply':
            quote = self.get_legal_quote(comment_text)
            reply = quote.replace('{user}', f'/u/{comment.author.name}') # personalize some quotes
            reply = reply.replace('{OP}', f'/u/{comment.submission.author.name}')
            reply = reply.replace('{sub}', f'/r/{comment.subreddit.display_name}')
            try:                           # try to reply to the comment
              comment.reply(reply)
            except APIException as e: # in case of too many requests, propagate the error
              raise e                 # to the outer try, wait and try again
            else:
              print(comment_text)
              print(reply)
              self.register_reply(comment_id)
      except KeyboardInterrupt:
        self.log('Logging off reddit..\n')
        break
      except APIException as e: # most likely due to frequency of requests. Wait before retrying
        if self.USER_NAME in [c.author.name for c in comment.replies]:
          self.register_reply(comment_id)
        self.log(str(e))
        self.log(comment_text)
        time.sleep(10)

if __name__ == '__main__':
  bot = ReplyBot()
  bot.reply_bot()
