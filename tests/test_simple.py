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
        yield from proc.start()
        yield from proc.terminated
        yield from proc.stop()
        self.assertEqual((yield from proc.terminated), 0)

    @async_test
    def test_oneshot(self):
        config = unitd.config.Config()
        config.service.syslog_identifier = "test"
        config.service.exec_start.append(["/bin/true"])
        proc = OneshotProcess(config, loop=self.loop)
        yield from proc.start()
        yield from proc.terminated
        yield from proc.stop()
        self.assertEqual((yield from proc.terminated), 0)

    @async_test
    def test_simple(self):
        config = unitd.config.Config()
        config.service.syslog_identifier = "test"
        config.service.exec_start.append(["/bin/sleep", "3600"])
        proc = SimpleProcess(config, loop=self.loop)
        yield from proc.start()
        yield from proc.stop()
        self.assertEqual((yield from proc.terminated), -15)

    @async_test
    def test_pre_post(self):
        config = unitd.config.Config()
        config.service.syslog_identifier = "test"
        config.service.exec_start_pre.append(["mkdir", "one"])
        config.service.exec_start_pre.append("-/bin/false")
        config.service.exec_start_pre.append(["-/bin/false"])
        config.service.exec_start_pre.append(["mkdir", "two"])
        config.service.exec_start.append(["/bin/sleep", "3600"])
        config.service.exec_start_post.append(["mkdir", "three"])
        with tempfile.TemporaryDirectory() as pathname:
            config.service.working_directory = pathname
            proc = SimpleProcess(config, loop=self.loop)

            yield from proc.start()
            self.assertTrue(os.path.isdir(os.path.join(pathname, "one")))
            self.assertTrue(os.path.isdir(os.path.join(pathname, "two")))
            self.assertTrue(os.path.isdir(os.path.join(pathname, "three")))
            yield from proc.stop()
            self.assertEqual((yield from proc.terminated), -15)
