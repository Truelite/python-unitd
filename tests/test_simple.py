import unittest
import functools
from unitd import SimpleProcess
from unitd.unittest import async_test, AsyncTestCase
import asyncio


class TestProcess(AsyncTestCase):
    @async_test
    def test_simple(self):
        proc = SimpleProcess("test", service={
            "ExecStart": ["/bin/true"],
        }, loop=self.loop)
        yield from proc.start()

    @async_test
    def test_task(self):
        proc = SimpleProcess("test", service={
            "ExecStart": ["/bin/true"],
        }, loop=self.loop)
        task = proc.start()
        yield from proc.started
        result = yield from proc.returncode
        self.assertEqual(result, 0)
        yield from task
