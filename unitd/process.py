import asyncio
import sys
import os
import shlex
import logging

log = logging.getLogger("unitd.process")

class Process:
    """
    [Service]
    SyslogIdentifier: string
    ExecStart: [ strings|arg sequence ]
     # @ prefix is not supported
     # - prefix is not supported
     # + prefix is not supported
    """
    def __init__(self, name, unit=None, service=None, loop=None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.name = name
        self.unit = unit if unit is not None else {}
        self.service = service if service is not None else {}
        self.log_tag = self.service.get("SyslogIdentifier", name)
        self.returncode = self.loop.create_future()


class SimpleProcess(Process):
    """
    Run a command, track its execution, log its standard output and standard
    error
    """
    def __init__(self, name, unit=None, service=None, preexec_fn=None, env=None, loop=None):
        super().__init__(name, unit, service, loop=loop)
        self.proc = None
        self.stdout_logger = None
        self.stderr_logger = None
        self.preexec_fn = preexec_fn
        self.env = env

    def _preexec(self):
        if self.preexec_fn:
            self.preexec_fn()
        os.setpgrp()

    def _get_cmdline(self):
        cmdline = self.service["ExecStart"]
        if len(cmdline) != 1:
            raise RuntimeError("ExecStart should only have one entry for simple processes")
        cmdline = cmdline[0]
        if isinstance(cmdline, str):
            return shlex.split(cmdline)
        return cmdline

    @asyncio.coroutine
    def start(self):
        """
        Start execution of the command, and logging of its stdout and stderr
        """
        cmdline = self._get_cmdline()
        log.debug("%s: cmdline: %s", self.log_tag, " ".join(shlex.quote(x) for x in cmdline))

        kw = {}
        if self.env is not None:
            kw["env"] = self.env

        # TODO: in the future, stdin could be connected to webrun's stdin, so
        # that one can pipe output to an X client exported to a web page
        self.proc = yield from asyncio.create_subprocess_exec(
            *cmdline, preexec_fn=self._preexec,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            loop=self.loop,
            **kw,
        )
        self.log_tag += "[{}]".format(self.proc.pid)
        self.stdout_logger = self.loop.create_task(self._log_fd("stdout", self.proc.stdout))
        self.stderr_logger = self.loop.create_task(self._log_fd("stderr", self.proc.stderr))

    @asyncio.coroutine
    def _log_fd(self, prefix, fd):
        while True:
            line = yield from fd.readline()
            if not line: break
            log.debug("%s:%s: ", self.log_tag, line.decode('utf8').rstrip())

    @asyncio.coroutine
    def wait_or_terminate(self, wait_time=1):
        """
        Wait for the program to quit, calling terminate() on it if it does not
        """
        #if self.proc.returncode is not None:
        #    log.debug("%s: exited with result %d", self.name, self.proc.returncode)
        #    return

        while True:
            try:
                result = yield from asyncio.wait_for(self.proc.wait(), wait_time, loop=self.loop)
            except asyncio.TimeoutError:
                pass
            else:
                log.debug("%s: exited with result %d", self.log_tag, self.proc.returncode)
                self.stdout_logger.cancel()
                self.stderr_logger.cancel()
                self.returncode.set_result(result)
                return
            
            log.debug("%s: terminating", self.log_tag)
            self.proc.terminate()

    @asyncio.coroutine
    def run(self):
        yield from self.start()
        yield from self.wait_or_terminate()
