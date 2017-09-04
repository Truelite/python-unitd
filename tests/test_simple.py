import unittest
import tempfile
import os
from unitd import SimpleProcess, OneshotProcess
from unitd.unittest import async_test, AsyncTestCase
import unitd.config
import asyncio


class TestProcess(AsyncTestCase):
    @async_test
    def test_quits(self):
        config = unitd.config.Config()
        config.service.syslog_identifier = "test"
        config.service.exec_start.append(["/bin/true"])
        proc = SimpleProcess(config, loop=self.loop)
        proc.start()
        yield from proc.started
        yield from proc.proc.wait()
        self.assertEqual((yield from proc.returncode), 0)

    @async_test
    def test_oneshot(self):
        config = unitd.config.Config()
        config.service.syslog_identifier = "test"
        config.service.exec_start.append(["/bin/true"])
        proc = OneshotProcess(config, loop=self.loop)
        yield from proc.start()
        self.assertEqual((yield from proc.returncode), 0)

    @async_test
    def test_simple(self):
        config = unitd.config.Config()
        config.service.syslog_identifier = "test"
        config.service.exec_start.append(["/bin/sleep", "3600"])
        proc = SimpleProcess(config, loop=self.loop)
        proc.start()
        yield from proc.started
        proc.task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            yield from proc.task

    @async_test
    def test_task(self):
        config = unitd.config.Config()
        config.service.syslog_identifier = "test"
        config.service.exec_start.append(["/bin/sleep", "3600"])
        proc = SimpleProcess(config, loop=self.loop)
        task = proc.start()
        yield from proc.started
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            yield from task
        result = yield from proc.returncode
        self.assertEqual(result, -15)

    @async_test
    def test_pre_post(self):
        config = unitd.config.Config()
        config.service.syslog_identifier = "test"
        config.service.exec_start_pre.append(["mkdir", "one"])
        config.service.exec_start_pre.append(["mkdir", "two"])
        config.service.exec_start.append(["/bin/sleep", "3600"])
        config.service.exec_start_post.append(["mkdir", "three"])
        with tempfile.TemporaryDirectory() as pathname:
            config.service.working_directory = pathname
            proc = SimpleProcess(config, loop=self.loop)

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
