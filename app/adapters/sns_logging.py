"""Redact OAuth callback queries and resumable capabilities from HTTP access logs."""

import logging


class SnsAccessFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if str(args[2]).startswith("/sns/"):
                args[2] = str(args[2]).split("?", 1)[0]
                record.args = tuple(args)
        return True


class GoogleHttpFilter(logging.Filter):
    def filter(self, record):
        # httpx INFO records can contain resumable session URLs, which are capabilities.
        return "googleapis.com" not in record.getMessage()
