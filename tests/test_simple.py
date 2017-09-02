import unittest
import tempfile
import os
from unitd import SimpleProcess, OneshotProcess
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
    def test_oneshot(self):
        proc = OneshotProcess("test", service={
            "ExecStart": [["/bin/true"]],
        }, loop=self.loop)
        yield from proc.start()
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

    @async_test
    def test_pre_post(self):
        with tempfile.TemporaryDirectory() as pathname:
            proc = SimpleProcess("test", service={
                "ExecStartPre": [["mkdir", "one"], ["mkdir", "two"]],
                "ExecStart": [["sleep", "3600"]],
                "ExecStartPost": [["mkdir", "three"]],
                "WorkingDirectory": pathname,
            }, loop=self.loop)

            task = proc.start()
            yield from proc.started
            self.assertTrue(os.path.isdir(os.path.join(pathname, "one")))
            self.assertTrue(os.path.isdir(os.path.join(pathname, "two")))
            self.assertTrue(os.path.isdir(os.path.join(pathname, "three")))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                yield from task
            result = yield from proc.returncode
            self.assertEqual(result, -15)
