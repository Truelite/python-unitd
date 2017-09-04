import asyncio
import sys
import os
import shlex
import logging

__ALL__ = ("SimpleProcess", "OneshotProcess")

log = logging.getLogger("unitd.process")


class ProcessLogger:
    def __init__(self, config, loop=None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.base_log_tag = config.service.syslog_identifier
        self.log_tag = self.base_log_tag
        self.stdout_logger = None
        self.stderr_logger = None

    @asyncio.coroutine
    def _log_fd(self, prefix, fd):
        while True:
            line = yield from fd.readline()
            if not line: break
            log.debug("%s:%s", self.log_tag, line.decode('utf8').rstrip())

    def get_subprocess_kwargs(self, **kw):
        kw["stdout"] = asyncio.subprocess.PIPE
        kw["stderr"] = asyncio.subprocess.PIPE
        return kw

    def start(self, proc):
        self.log_tag = self.base_log_tag + "[{}]".format(proc.pid)
        self.stdout_logger = self.loop.create_task(self._log_fd("stdout", proc.stdout))
        self.stderr_logger = self.loop.create_task(self._log_fd("stderr", proc.stderr))

    def stop(self):
        self.stdout_logger.cancel()
        self.stderr_logger.cancel()
        self.log_tag = self.base_log_tag


class Process:
    """
    [Service]
    SyslogIdentifier: string
    ExecStart: [ strings|arg sequence ]
     # @ prefix is not supported
     # - prefix is not supported
     # + prefix is not supported
    ExecStartPre: [ strings|arg sequence ]
     # - prefix is not supported
    ExecStartPost: [ strings|arg sequence ]
     # - prefix is not supported
    WorkingDirectory:
     # ~ is not supported
    """
    def __init__(self, config, loop=None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.config = config
        self.logger = ProcessLogger(config, self.loop)
        # Future set to True when the process has started
        self.started = self.loop.create_future()
        # Future set to the process return code when it quits
        self.returncode = self.loop.create_future()
        self.task = None

    def _get_subprocess_kwargs(self):
        kw = self.config.service.get_subprocess_kwargs(loop=self.loop)
        kw = self.logger.get_subprocess_kwargs(**kw)
        return kw

    @asyncio.coroutine
    def exec_wait(self, cmdline):
        if isinstance(cmdline, str):
            cmdline = shlex.split(cmdline)
        log.debug("%s:starting: %s", self.logger.log_tag, " ".join(shlex.quote(x) for x in cmdline))

        kw = self._get_subprocess_kwargs()
        if self.env is not None:
            kw["env"] = self.env

        proc = yield from asyncio.create_subprocess_exec(
            *cmdline,
            stdin=asyncio.subprocess.DEVNULL,
            **kw,
        )
        self.logger.start(proc)

        yield from proc.wait()

        log.debug("%s:exited with result %d: %s", self.logger.log_tag, proc.returncode, " ".join(shlex.quote(x) for x in cmdline))
        self.logger.stop()

        return proc.returncode

    @asyncio.coroutine
    def _run_exec_start_pre(self):
        for cmd in self.config.service.exec_start_pre:
            if (yield from self.exec_wait(cmd)) != 0:
                break

    @asyncio.coroutine
    def _run_exec_start_post(self):
        for cmd in self.config.service.exec_start_post:
            if (yield from self.exec_wait(cmd)) != 0:
                break

    @asyncio.coroutine
    def _run_coroutine(self):
        try:
            yield from self._run_exec_start_pre()
            yield from self._start()
            if not self.started.cancelled():
                yield from self._run_exec_start_post()
                self.started.set_result(True)
            else:
                return
            yield from self.proc.wait()
            log.debug("%s:exited", self.logger.log_tag)
        finally:
            if self.task.cancelled():
                log.debug("%s:cancelled", self.logger.log_tag)
            yield from self._wait_or_terminate()

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
                log.debug("%s:exited with result %d", self.logger.log_tag, self.proc.returncode)
                self.logger.stop()
                if not self.returncode.cancelled():
                    self.returncode.set_result(result)
                return

            log.debug("%s:terminating", self.logger.log_tag)
            self.proc.terminate()

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


class OneshotProcess(Process):
    def __init__(self, config, preexec_fn=None, env=None, loop=None):
        super().__init__(config, loop=loop)
        self.proc = None
        self.preexec_fn = preexec_fn
        self.env = env

    @asyncio.coroutine
    def _start(self):
        """
        Start execution of the command, and logging of its stdout and stderr
        """
        for cmdline in self.config.service.exec_start:
            # TODO: this starts in parallel, but oneshot should start serially
            if isinstance(cmdline, str):
                cmdline = shlex.split(cmdline)
            log.debug("%s:cmdline: %s", self.logger.log_tag, " ".join(shlex.quote(x) for x in cmdline))

            kw = self._get_subprocess_kwargs()
            if self.env is not None:
                kw["env"] = self.env

            self.proc = yield from asyncio.create_subprocess_exec(
                *cmdline,
                stdin=asyncio.subprocess.DEVNULL,
                **kw,
            )
            self.logger.start(self.proc)
        return True


class SimpleProcess(Process):
    """
    Run a command, track its execution, log its standard output and standard
    error
    """
    def __init__(self, config, preexec_fn=None, env=None, loop=None):
        super().__init__(config, loop=loop)
        self.proc = None
        self.preexec_fn = preexec_fn
        self.env = env

    def _preexec(self):
        if self.preexec_fn:
            self.preexec_fn()
        os.setpgrp()

    def _get_cmdline(self):
        if len(self.config.service.exec_start) != 1:
            raise RuntimeError("ExecStart should only have one entry for simple processes")
        cmdline = self.config.service.exec_start[0]
        if isinstance(cmdline, str):
            return shlex.split(cmdline)
        return cmdline

    @asyncio.coroutine
    def _start(self):
        """
        Start execution of the command, and logging of its stdout and stderr
        """
        cmdline = self._get_cmdline()
        log.debug("%s:cmdline: %s", self.logger.log_tag, " ".join(shlex.quote(x) for x in cmdline))

        kw = self._get_subprocess_kwargs()
        if self.env is not None:
            kw["env"] = self.env

        # TODO: in the future, stdin could be connected to webrun's stdin, so
        # that one can pipe output to an X client exported to a web page
        self.proc = yield from asyncio.create_subprocess_exec(
            *cmdline, preexec_fn=self._preexec,
            stdin=asyncio.subprocess.DEVNULL,
            **kw,
        )
        self.logger.start(self.proc)

        done, pending = yield from asyncio.wait((
            self._confirm_start(),
            self.proc.wait()), return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()

        if self.proc.returncode is not None:
            log.warn("%s:failed to start (exited with code %d)", self.logger.log_tag, self.proc.returncode)
            return False
        else:
            log.debug("%s:started", self.logger.log_tag)
            return True

    @asyncio.coroutine
    def _confirm_start(self):
        """
        Wait until confirmation that the process has successfully started
        """
        pass
