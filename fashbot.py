"""Macros and toolbox integration for moderation"""

from base64 import b64decode
import json
import os
import random
import signal
import sys
import time
from typing import Deque
from zlib import decompress

import praw
import prawcore

from slack_python_logging import slack_logger


class FashBot:
    """Main bot class"""

    def __init__(self):
        """Initialize class, requires appropriate environment variables"""
        self.reddit = praw.Reddit(
            client_id = os.environ["client_id"],
            client_secret = os.environ["client_secret"],
            refresh_token = os.environ["refresh_token"],
            user_agent = "linux:fashbot:v0.1 (by /u/jenbanim)"
        )
        self.subreddit = self.reddit.subreddit(os.environ["subreddit"])
        self.logger = slack_logger.initialize(
            app_name = "fashbot", 
            stream_loglevel = "DEBUG",
            slack_loglevel = "CRITICAL"
        )
        self.parsed = Deque(maxlen=200) # List of comment ids, to avoid repeats
        self.start_time = time.time()


    def listen(self):
        """Listen for comments/PMs and handle them"""
        reddit_api_errors = (
            prawcore.exceptions.ServerError,
            prawcore.exceptions.ResponseException,
            prawcore.exceptions.RequestException
        )
        mods = self.subreddit.moderator()
        try:
            for comment in self.subreddit.stream.comments(pause_after=1):
                # It would be easier to use username pings to summon the bot
                # but those don't show up when removed, even for mods -_-
                if comment is None:
                    # No new comments to read, so let's take a break
                    break
                if comment.created_utc < self.start_time:
                    # Don't trigger on comments posted prior to startup
                    continue
                if comment.id in self.parsed:
                    # Don't trigger on comments that have already been handled
                    continue
                if comment.author not in mods:
                    # Don't trigger on comments from the unwashed masses
                    continue
                if "!fashbot" in comment.body.lower():
                    self.handle_comment(comment)
                    self.parsed.append(comment.id)
            for item in self.reddit.inbox.unread(limit=1):
                if isinstance(item, praw.models.Message):
                    # Don't trigger on comment replies or pings
                    if item.created_utc > self.start_time:
                        # Don't trigger on PMs sent prior to startup
                        if item.author in mods():
                            # Again, no plebs
                            self.handle_message(item)
                item.mark_read()
        except reddit_api_errors:
            self.logger.error("Error reaching Reddit, sleeping 1 minute")
            time.sleep(60)


    def handle_comment(self, comment):
        """Reply fashily to comment summons with command options
        
        By putting the data about the comment type and ID in the subject, we
        know what content is being referred to in subsequent messages
        """
        self.logger.debug("handling comment %s", comment.id)
        usernotes = self.get_usernotes(comment.parent().author)
        if not usernotes:
            usernotes = "No usernotes"
        comment.author.message(subject="usernotes", message=usernotes)
        #parent = comment.parent()
        #if isinstance(parent, praw.models.Comment):
        #    content_type = "comment"
        #if isinstance(parent, praw.models.Submission):
        #    content_type = "submission"
        #subject = f"{content_type} {parent.id} summons"
        #with open("dialogue/summon_response.txt") as f:
        #    body = random.choice(f.readlines())
        #with open("dialogue/commands.txt") as f:
        #    body += f.read()
        #comment.author.message(subject=subject, message=body)


    def handle_message(self, message):
        """Respond fashily to messages with requested action"""
        self.logger.debug("Handling message %s", message.id)
        # Should just strip off the "re:"
        _, content_type, content_id, state = message.subject.split()
        if content_type == "comment":
            content = self.reddit.comment(id=content_id)
        elif content_type == "submission":
            content = self.reddit.submission(id=content_id)
        command = message.body.lower()
        # This is where more complicated logic will go for state-dependent
        # actions like adding usernotes or banning someone. But for now it can
        # only reply with usernotes
        body = self.get_usernotes(content.author)
        with open("dialogue/commands.txt") as f:
            body += f.read()
        message.author.message(subject=message.subject, message=str(usernotes))


    def get_usernotes(self, user):
        """Load and format a user's notes from subreddit wiki"""
        self.logger.debug("Getting usernotes for %s", user.name)
        user = str(user) # Allows for user to be str or redditor instance
        usernotes = json.loads(self.subreddit.wiki["usernotes"].content_md)
        constants = usernotes["constants"]
        notes = json.loads(
            decompress(b64decode(usernotes["blob"])).decode("utf-8")
        )
        formatted_notes = []
        if user in notes:
            for note in notes[user]["ns"]:
                note_mod = constants["users"][note["m"]]
                note_time = time.strftime(
                    "%Y-%m-%d %H:%M:%S",
                    time.localtime(note["t"])
                )
                note_reason = constants["warnings"][note["w"]]
                note_text = note["n"]
                note_link_split = note["l"].split(",")
                if len(note_link_split) == 1:
                    # No link
                    note_link = ""
                if len(note_link_split) == 2:
                    # Submission link
                    thread_id = note_link_split[1]
                    sub = self.subreddit.display_name
                    note_link = (
                        f"https://reddit.com/r/{sub}/comments/{thread_id}"
                    )
                if len(note_link_split) == 3:
                    # Comment link
                    thread_id = note_link_split[1]
                    comment_id = note_link_split[2]
                    sub = self.subreddit.display_name
                    note_link = (
                        f"https://reddit.com/r/{sub}/comments/{thread_id}"
                        f"/_/{comment_id}"
                    )
                if note_link:
                    formatted_notes.append(
                        f"{note_mod} | [{note_time}]({note_link}) | "
                        f"{note_reason} | {note_text}"
                    )
                else:
                    formatted_notes.append(
                        f"{note_mod} | {note_time} | {note_reason} | "
                        f"{note_text}"
                    )
        if formatted_notes:
            header = ["Mod | Time | Reason | Note", "- | - | - | - | -"]
            formatted_notes = header + formatted_notes
        return "\n".join(formatted_notes)


if __name__ == "__main__":
    """Main program loop. Create a fashbot instance and listen continuously."""
    fashbot = FashBot()
    while True:
        fashbot.listen()
        time.sleep(3)
