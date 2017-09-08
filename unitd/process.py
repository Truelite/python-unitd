import asyncio
import signal
import sys
import os
import shlex
import logging

__ALL__ = ("SimpleProcess", "OneshotProcess")

log = logging.getLogger("unitd.process")


class ProcessLogger:
    """
    Handle logging of stdout and stderr from a running process
    """
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
        """
        Hook used when constructing arguments for
        asyncio.create_subprocess_exec
        """
        kw["stdout"] = asyncio.subprocess.PIPE
        kw["stderr"] = asyncio.subprocess.PIPE
        return kw

    def start(self, proc):
        """
        Start the logging tasks for the given process
        """
        self.log_tag = self.base_log_tag + "[{}]".format(proc.pid)
        self.stdout_logger = self.loop.create_task(self._log_fd("stdout", proc.stdout))
        self.stderr_logger = self.loop.create_task(self._log_fd("stderr", proc.stderr))

    def stop(self):
        """
        Stop the logging tasks
        """
        self.stdout_logger.cancel()
        self.stderr_logger.cancel()
        self.log_tag = self.base_log_tag


class Process:
    """
    Base class for processes managed by unitd
    """
    def __init__(self, config, env=None, loop=None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.config = config
        self.env = env
        self.logger = ProcessLogger(config, self.loop)
        self._last_exit_code = None
        # Set to True when start succeeds, False when start fails
        self.started = self.loop.create_future()
        # Future set to the process exit code when it exits
        self.terminated = None
        # Set to True when stop succeeds
        self.stopped = self.loop.create_future()

    def _preexec(self):
        """
        Hook passed as preexec_fn to the child process
        """
        # Set user and group id
        if os.getgid() == 0 and self.config.service.group != 0:
            os.setgid(self.config.service.group)
        if os.getuid() == 0 and self.config.service.user != 0:
            os.setuid(self.config.service.user)

    def _get_subprocess_kwargs(self):
        """
        Hook used when constructing arguments for
        asyncio.create_subprocess_exec
        """
        kw = self.config.service.get_subprocess_kwargs(loop=self.loop, preexec_fn=self._preexec)
        kw = self.logger.get_subprocess_kwargs(**kw)
        if self.env is not None:
            kw["env"] = self.env
        return kw

    def _parse_cmdline(self, cmdline, flags=""):
        """
        Turn cmdline into a list of command line arguments.

        If cmdline is already a list, it is preserved as is.

        If flags is not empty, leading characters from flags in cmdline (or in
        the first element of cmdline if it is a list) are stripped, and
        returned separately.

        Returns (cmdline:list, flags:str)
        """
        if isinstance(cmdline, str):
            cmdline = shlex.split(cmdline)

        stripped = cmdline[0].lstrip(flags)
        if stripped == cmdline[0]:
            return cmdline, ""
        else:
            _flags = cmdline[0][:len(stripped)]
            cmdline[0] = stripped
            return cmdline, _flags

    @asyncio.coroutine
    def exec_wait(self, cmdline):
        """
        Run the given command line and wait for its completion.

        stdout and stderr are logged with self.logger
        """
        cmdline, flags = self._parse_cmdline(cmdline, "-")

        log.debug("%s:starting: %s", self.logger.log_tag, " ".join(shlex.quote(x) for x in cmdline))

        kw = self._get_subprocess_kwargs()
        proc = yield from asyncio.create_subprocess_exec(
            *cmdline,
            stdin=asyncio.subprocess.DEVNULL,
            **kw
        )
        self.logger.start(proc)

        self._last_exit_code = yield from proc.wait()

        log.debug("%s:exited with result %d: %s", self.logger.log_tag, proc.returncode, " ".join(shlex.quote(x) for x in cmdline))
        self.logger.stop()

        if "-" in flags:
            return True
        return proc.returncode == 0

    @asyncio.coroutine
    def _run_sync_commands(self, commands):
        """
        Run commands from the `commands` list, stopping at the first that fails
        """
        for cmd in commands:
            if not (yield from self.exec_wait(cmd)):
                return False
        return True

    @asyncio.coroutine
#    def _run_coroutine(self):
#        try:
#            yield from self._start()
#            if not self.started.cancelled():
#                yield from self._run_sync_commands(self.config.service.exec_start_post)
#                self.started.set_result(True)
#            else:
#                return
#            yield from self.proc.wait()
#            log.debug("%s:exited", self.logger.log_tag)
#        finally:
#            if self.task.cancelled():
#                log.debug("%s:cancelled", self.logger.log_tag)
#            yield from self._wait_or_terminate()

    @asyncio.coroutine
    def start(self):
        """
        Start the process.

        Return True if the process was started successfully, False if something
        failed.
        """
        if not (yield from self._run_sync_commands(self.config.service.exec_start_pre)):
            self.started.set_result(False)
            return False
        log.debug("%s:exec_start_pre succeeded", self.logger.log_tag)

        if not (yield from self._start()):
            self.started.set_result(False)
            return False
        log.debug("%s:exec_start succeeded", self.logger.log_tag)

        if not (yield from self._run_sync_commands(self.config.service.exec_start_post)):
            self.started.set_result(False)
            return False
        log.debug("%s:exec_start_post succeeded", self.logger.log_tag)

        self.started.set_result(True)
        return True

    @asyncio.coroutine
    def stop(self):
        """
        Stop the process
        """
        if self.started.done() and self.started.result():
            yield from self._run_sync_commands(self.config.service.exec_stop)
        yield from self._kill()
        yield from self._run_sync_commands(self.config.service.exec_stop_post)
        self.stopped.set_result(True)

    @asyncio.coroutine
    def _kill(self):
        """
        Kill the program
        """
        if not self.started.done():
            raise RuntimeError("{}:_kill called on a process that has not been started yet".format(self.logger.log_tag))

        try:
            if self.terminated.done():
                return

            if self.config.service.kill_mode == "none":
                return

            log.debug("%s:sending %d signal", self.logger.log_tag, self.config.service.kill_signal)
            self.proc.send_signal(self.config.service.kill_signal)

            try:
                result = yield from asyncio.wait_for(self.proc.wait(), self.config.service.timeout_stop_sec, loop=self.loop)
            except asyncio.TimeoutError:
                result = None

            if result is None and self.config.service.send_sigkill:
                log.debug("%s:sending %d signal", self.logger.log_tag, signal.SIGKILL)
                self.proc.send_signal(signal.SIGKILL)

                try:
                    result = yield from asyncio.wait_for(self.proc.wait(), self.config.service.timeout_stop_sec, loop=self.loop)
                except asyncio.TimeoutError:
                    result = None

                if result is None:
                    log.debug("%s:did not respond to SIGKILL: giving up", self.logger.log_tag)
                else:
                    log.debug("%s:exited with result code %d", self.logger.log_tag, result)
        finally:
            self.logger.stop()


class OneshotProcess(Process):
    @asyncio.coroutine
    def _start(self):
        """
        Start execution of the command, and logging of its stdout and stderr
        """
        self.terminated = self.loop.create_future()

        try:
            if not (yield from self._run_sync_commands(self.config.service.exec_start)):
                return False

            return True
        finally:
            self.terminated.set_result(self._last_exit_code)

    @asyncio.coroutine
    def _wait_or_terminate(self, wait_time=1):
        pass


class SimpleProcess(Process):
    """
    Run a command, track its execution, log its standard output and standard
    error
    """
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.proc = None
        if len(self.config.service.exec_start) != 1:
            raise RuntimeError("ExecStart should only have one entry for simple processes")
        self.cmdline, self.flags = self._parse_cmdline(self.config.service.exec_start[0], "-+@")

    def _preexec(self):
        super()._preexec()
        os.setpgrp()

    @asyncio.coroutine
    def _start(self):
        """
        Start execution of the command, and logging of its stdout and stderr
        """
        log.debug("%s:cmdline: %s", self.logger.log_tag, " ".join(shlex.quote(x) for x in self.cmdline))

        kw = self._get_subprocess_kwargs()

        self.proc = yield from asyncio.create_subprocess_exec(
            *self.cmdline, stdin=asyncio.subprocess.DEVNULL, **kw
        )
        self.logger.start(self.proc)

        # Run self._confirm_start to give subclassers a way to detect when the
        # startup is done, like polling on a tcp port, or waiting for a signal
        done, pending = yield from asyncio.wait((
            self._confirm_start(),
            self.proc.wait()), return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()

        try:
            if self.proc.returncode is not None:
                log.warn("%s:failed to start (exited with code %d)", self.logger.log_tag, self.proc.returncode)
                return False
            else:
                log.debug("%s:started", self.logger.log_tag)
                return True
        finally:
            self.terminated = self.loop.create_task(self.proc.wait())

    @asyncio.coroutine
    def _confirm_start(self):
        """
        Wait until confirmation that the process has successfully started
        """
        pass
