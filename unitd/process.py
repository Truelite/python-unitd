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
        # Future set to True when the process has started
        self.started = self.loop.create_future()
        # Future set to the process return code when it quits
        self.returncode = self.loop.create_future()
        self.task = None

    @asyncio.coroutine
    def _run_coroutine(self):
        try:
            yield from self._start()
            if not self.started.cancelled():
                self.started.set_result(True)
            else:
                return
            yield from self.proc.wait()
            log.debug("%s:exited", self.log_tag)
        finally:
            if self.task.cancelled():
                log.debug("%s:cancelled", self.log_tag)
            yield from self._wait_or_terminate()

    def start(self):
        """
        Create and schedule a task that starts the process and waits for its
        completion.

        If the task gets canceled, it will still make sure the underlying
        process gets killed.

        If the process has already been started, returns the existing task
        """
        if self.task is None:
            self.task = self.loop.create_task(self._run_coroutine())
        return self.task


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
    def _start(self):
        """
        Start execution of the command, and logging of its stdout and stderr
        """
        cmdline = self._get_cmdline()
        log.debug("%s:cmdline: %s", self.log_tag, " ".join(shlex.quote(x) for x in cmdline))

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

        done, pending = yield from asyncio.wait((
            self._confirm_start(),
            self.proc.wait()), return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()

        if self.proc.returncode is not None:
            log.warn("%s:failed to start (exited with code %d)", self.log_tag, self.proc.returncode)
            return False
        else:
            log.debug("%s:started", self.log_tag)
            return True

    @asyncio.coroutine
    def _confirm_start(self):
        """
        Wait until confirmation that the process has successfully started
        """
        pass

    @asyncio.coroutine
    def _log_fd(self, prefix, fd):
        while True:
            line = yield from fd.readline()
            if not line: break
            log.debug("%s:%s", self.log_tag, line.decode('utf8').rstrip())

    @asyncio.coroutine
    def _wait_or_terminate(self, wait_time=1):
        """
        Wait for the program to quit, calling terminate() on it if it does not
        """
        while True:
            try:
                result = yield from asyncio.wait_for(self.proc.wait(), wait_time, loop=self.loop)
            except asyncio.TimeoutError:
                pass
            else:
                log.debug("%s:exited with result %d", self.log_tag, self.proc.returncode)
                self.stdout_logger.cancel()
                self.stderr_logger.cancel()
                if not self.returncode.cancelled():
                    self.returncode.set_result(result)
                return
            
            log.debug("%s:terminating", self.log_tag)
            self.proc.terminate()
