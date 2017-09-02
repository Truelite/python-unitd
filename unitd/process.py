import asyncio
import sys
import os
import shlex
import logging

log = logging.getLogger("unitd.process")

class Process:
    def __init__(self, name, unit=None, service=None):
        self.name = name
        self.unit = unit if unit is not None else {}
        self.service = service if service is not None else {}


class SimpleProcess(Process):
    """
    Run a command, track its execution, log its standard output and standard
    error
    """
    def __init__(self, name, unit=None, service=None, preexec_fn=None, env=None):
        super().__init__(name, unit, service)
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
        log.debug("%s: cmdline: %s", self.name, " ".join(shlex.quote(x) for x in cmdline))

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
            **kw,
        )
        loop = asyncio.get_event_loop()
        self.stdout_logger = loop.create_task(self._log_fd("stdout", self.proc.stdout))
        self.stderr_logger = loop.create_task(self._log_fd("stderr", self.proc.stderr))

    @asyncio.coroutine
    def _log_fd(self, prefix, fd):
        while True:
            line = yield from fd.readline()
            if not line: break
            log.debug("%s:%s: ", self.name, line.decode('utf8').rstrip())

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
                result = yield from asyncio.wait_for(self.proc.wait(), wait_time)
            except asyncio.TimeoutError:
                pass
            else:
                log.debug("%s: exited with result %d", self.name, self.proc.returncode)
                return
            
            log.debug("%s: terminating", self.name)
            self.proc.terminate()
