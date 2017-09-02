import unittest
import functools
from unitd import SimpleProcess
from unitd.unittest import async_test, AsyncTestCase
import asyncio


class TestProcess(AsyncTestCase):
    @async_test
    def test_quits(self):
        proc = SimpleProcess("test", service={
            "ExecStart": [["/bin/true"]],
        }, loop=self.loop)
        proc.start()
        yield from proc.started
        yield from proc.proc.wait()
        self.assertEqual((yield from proc.returncode), 0)

    @async_test
    def test_simple(self):
        proc = SimpleProcess("test", service={
            "ExecStart": [["/bin/sleep", "3600"]],
        }, loop=self.loop)
        proc.start()
        yield from proc.started
        proc.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            yield from proc.task

    @async_test
    def test_task(self):
        proc = SimpleProcess("test", service={
            "ExecStart": [["/bin/sleep", "3600"]],
        }, loop=self.loop)
        task = proc.start()
        yield from proc.started
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            yield from task
        result = yield from proc.returncode
        self.assertEqual(result, -15)
