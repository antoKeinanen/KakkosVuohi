"""
Announcements shown once to every user, the first time they use the bot after an announcement
was added. Only ever append to the end of the list: users have read the first N of them.
New users start after the last announcement, so they never see the older ones.
"""

ANNOUNCEMENTS: list[str] = []
