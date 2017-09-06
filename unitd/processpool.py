import asyncio
import logging
from .signals import create_future_for_signal

log = logging.getLogger("unitd.processpool")


class ProcessPool:
    def __init__(self, loop=None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        # Future that will get a result if the quit signal is received
        self.quit_signal = None
        # Set to False when a process fails to start
        self.success = True
        # List of processes that we manage
        self.processes = []

    def set_quit_signal(self, sig):
        log.debug("Installing handler for signal %d", sig)
        self.quit_signal = create_future_for_signal(sig)

    @asyncio.coroutine
    def start_sync(self, process):
        if not self.success:
            log.debug("A previous process failed to start, %s will not be started", process.logger.log_tag)
            return False

        if self.quit_signal.done():
            log.debug("Quit signal received, %s will not be started", process.logger.log_tag)
            return False

        log.debug("Starting process %s synchronously", process.logger.log_tag)
        res = yield from process.start()
        if not res:
            self.success = False
        self.processes.append(process)
        return self.success

    @asyncio.coroutine
    def run(self):
        try:
            if not self.success:
                return

            wait_for = [p.terminated for p in self.processes]
            if self.quit_signal:
                wait_for.append(self.quit_signal)

            done, pending = yield from asyncio.wait(
                wait_for,
                return_when=asyncio.FIRST_COMPLETED,
                loop=self.loop)
        finally:
            yield from asyncio.wait(
                [p.stop() for p in self.processes],
                return_when=asyncio.ALL_COMPLETED)
