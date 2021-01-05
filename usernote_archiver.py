"""Maintains a write-only copy of our usernotes for archival purposes"""

from base64 import b64decode
import json
import os
import time
from zlib import decompress

import praw
import prawcore

from slack_python_logging import slack_logger


class UsernoteArchiver:
    """Main bot class"""

    def __init__(self):
        """Initialize class, requires appropriate environment variables"""
        self.reddit = praw.Reddit(
            client_id = os.environ["client_id"],
            client_secret = os.environ["client_secret"],
            refresh_token = os.environ["refresh_token"],
            user_agent = "linux:usernote_archiver:v0.1 (by /u/jenbanim)"
        )
        self.subreddit = self.reddit.subreddit(os.environ["subreddit"])
        self.logger = slack_logger.initialize(
            app_name = "Usernote Archiver", 
            stream_loglevel = "DEBUG",
            slack_loglevel = "CRITICAL"
        )


    def archive_usernotes(self):
        """Save any new usernotes to local storage"""
        self.logger.debug("Beginning to archive usernotes")
        with open("archived_usernotes.json") as f:
            archived_usernotes = json.load(f)
        subreddit_usernotes = json.loads(self.subreddit.wiki["usernotes"].content_md)
        subreddit_usernotes["blob"] = json.loads(
            decompress(b64decode(subreddit_usernotes["blob"])).decode("utf-8")
        )

        # Kill the bot if version mismatch
        assert archived_usernotes["ver"] == subreddit_usernotes["ver"]

        self.logger.debug("Updating mods")
        for idx, mod in enumerate(subreddit_usernotes["constants"]["users"]):
            # New mods should be appended to this list
            # If any have been removed or substituted we've got a problem
            try:
                assert mod == archived_usernotes["constants"]["users"][idx]
            except IndexError:
                self.logger.info("Adding new mod %s", mod)
                archived_usernotes["constants"]["users"].append(mod)

        self.logger.debug("Updating warnings")
        for idx, warning in enumerate(subreddit_usernotes["constants"]["warnings"]):
            # New warnings should be appended, as with mods
            try:
                assert warning == archived_usernotes["constants"]["warnings"][idx]
            except IndexError:
                self.logger.info("Adding new warning %s", warning)
                archived_usernotes["constants"]["warnings"].append(warning)

        self.logger.debug("Updating notes")
        for user in subreddit_usernotes["blob"]:
            if user in archived_usernotes["blob"]:
                for note in subreddit_usernotes["blob"][user]["ns"]:
                    note_exists = False
                    for users_archived_note in archived_usernotes["blob"][user]["ns"]:
                        if note["t"] == users_archived_note["t"]:
                            note_exists = True
                    if note_exists:
                        continue
                    self.logger.info("Adding note for user %s", user)
                    archived_usernotes["blob"][user]["ns"].append(note)
            else:
                self.logger.info("Adding new user %s", user)
                archived_usernotes["blob"][user] = user

        self.logger.debug("Saving updated usernotes")
        with open("archived_usernotes.json", "w") as f:
            json.dump(archived_usernotes, f, indent=4)


if __name__ == "__main__":
    """Main program loop. Create a usernote_archiver instance and listen continuously."""
    usernote_archiver = UsernoteArchiver()
    while True:
        usernote_archiver.archive_usernotes()
        time.sleep(60 * 60 * 8) # Run every 8 hours
