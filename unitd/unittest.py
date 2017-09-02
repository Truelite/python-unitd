import unittest
import atexit
import asyncio
import functools

def async_test(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kw):
        coro = asyncio.coroutine(f)
        future = coro(self, *args, **kw)
        self.loop.run_until_complete(future)
    return wrapper


class AsyncTestCase(unittest.TestCase):
    _ioloop_closed = False

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self._orig_loop_debug = self.loop.get_debug()
        self.loop.set_debug(True)
        # TODO: find a way to have a private event loop for tests
        #self.orig_event_loop = asyncio.get_event_loop()
        #self.loop = asyncio.new_event_loop()
        ##self.loop.set_debug(True)
        #asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.set_debug(self._orig_loop_debug)
        #self.loop.close()
        #asyncio.set_event_loop(self.orig_event_loop)
        pass


    @classmethod
    def _atexit(cls):
        # TODO: see python issue 23548
        if not cls._ioloop_closed:
            asyncio.get_event_loop().close()


atexit.register(AsyncTestCase._atexit)
