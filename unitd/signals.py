import asyncio
import signal
import logging

log = logging.getLogger("unitd.signal")


def create_future_for_signal(signum=signal.SIGINT, loop=None):
    """
    Create a future that is set to True when the given signal is received
    """
    if loop is None:
        loop = asyncio.get_event_loop()

    def remove_handler(future):
        log.debug("Removing handler for signal %d", signum)
        loop.remove_signal_handler(signum)

    signal_received = asyncio.Future()
    signal_received.add_done_callback(remove_handler)

    # python3.5: signal_received = self.loop.create_future()
    def _on_signal():
        log.debug("Signal %d received", signum)
        signal_received.set_result(True)

    loop.add_signal_handler(signum, _on_signal)
    return signal_received
