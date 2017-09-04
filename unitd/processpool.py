import asyncio
import logging
from .signals import create_future_for_signal

log = logging.getLogger("unitd.processpool")


class ProcessPool:
    def __init__(self, loop=None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.tasks = []

    def set_quit_signal(self, sig):
        log.debug("Installing handler for signal %d", sig)
        self.tasks.append(create_future_for_signal(sig))

    @asyncio.coroutine
    def start_sync(self, process):
        log.debug("Starting process %s synchronously", process.logger.log_tag)
        self.tasks.append(process.start())
        yield from process.started

    def start_async(self, process):
        log.debug("Starting process %s ssynchronously", process.logger.log_tag)
        self.tasks.append(process.start())

    @asyncio.coroutine
    def run(self):
        done, pending = yield from asyncio.wait(
            self.tasks,
            return_when=asyncio.FIRST_COMPLETED,
            loop=self.loop)

        log.debug("%d tasks done, %d tasks pending", len(done), len(pending))

        for p in pending:
            p.cancel()

        yield from asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED, loop=self.loop)
