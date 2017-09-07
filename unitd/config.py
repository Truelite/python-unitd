import re
import os
import pwd
import grp
import signal
from contextlib import contextmanager
import logging

log = logging.getLogger("unitd.config")

class ParseError(RuntimeError):
    def __init__(self, fd, lineno, msg):
        self.fd = fd
        self.filename = getattr(fd, "name", None)
        self.lineno = lineno
        if self.filename is None:
            msg = "line {}:{}".format(self.lineno, msg)
        else:
            msg = "{}:{}:{}".format(self.filename, self.lineno, msg)
        super().__init__(self, msg)

re_empty = re.compile(r"^\s*(?:#|$)")
re_section = re.compile(r"^\[(?P<section>[^]]+)\]\s*$")
re_assign = re.compile(r"^\s*(?P<key>\w+)\s*=\s*(?P<val>.+?)\s*$")


class HostPort:
    """
    Hold a host:port pair
    """
    def __init__(self, host="localhost", port=None):
        self.host = host
        self.port = port

    def __str__(self):
        if self.host is not None:
            return "{}:{}".format(self.host, self.port)
        else:
            return str(self.port)

    @classmethod
    def parse(cls, s):
        mo = re.match(r"^(?:(?P<host>[^:]+):)?(?P<port>\d+)$", s)
        if not mo:
            raise ValueError("invalid [host:]port: `{}`".format(s))
        if mo.group("host"):
            return cls(host=mo.group("host"), port=int(mo.group("port")))
        else:
            return cls(port=int(mo.group("port")))


class Parser:
    def __init__(self, fd):
        self.fd = fd
        self.lineno = None

    def parse_error(self, msg):
        raise ParseError(self.fd, self.lineno, msg)

    def parse(self):
        current_section = None

        for self.lineno, line in enumerate(self.fd, start=1):
            if re_empty.match(line): continue

            mo = re_section.match(line)
            if mo:
                current_section = mo.group("section")
                continue

            mo = re_assign.match(line)
            if mo:
                if current_section is None:
                    self.parse_error("key=value line found outside all sections")
                yield current_section, mo.group("key"), mo.group("val")
                continue

            self.parse_error("line not recognised as comment, [section] or assignment")

    def parse_bool(self, s):
        if s.lower() in ("yes", "true", "1"):
            return True
        elif s.lower() in ("no", "false", "0"):
            return False
        else:
            self.parse_error("invalid bool value: `{}`".format(s))

    def parse_int(self, s):
        try:
            return int(s)
        except ValueError:
            self.parse_error("invalid integer value: `{}`".format(s))

    def parse_signal(self, s):
        if re.match("^[A-Z]+^", s):
            signum = getattr(signal, s, None)
            if signum is None:
                self.parse_error("invalid signal name: `{}`".format(s))
            return signum
        else:
            try:
                return int(s)
            except ValueError:
                self.parse_error("invalid signal number: `{}`".format(s))

    def parse_delay(self, s):
        if s == "infinity":
            return None
        if s.isdigit():
            return self.parse_int(s)
        re_delay = re.compile("^(?:(?P<min>\d+)min|(?P<sec>\d+)sec)$")
        res = 0
        for delay in s.split():
            mo = re_delay.match(delay)
            if not mo:
                self.parse_error("invalid time unit: `{}`".format(s))
            val = mo.group("min")
            if val is not None:
                res += int(val) * 60
                continue
            val = mo.group("sec")
            if val is not None:
                res += int(val)
        return res

    def parse_user(self, s):
        if s.startswith('$'):
            s = os.environ[s[1:]]
        if s.isdigit():
            return int(s)
        try:
            p = pwd.getpwnam(s)
        except KeyError:
            self.parse_error("invalid user name: `{}`".format(s))
        return p.pw_uid

    def parse_group(self, s):
        if s.startswith('$'):
            s = os.environ[s[1:]]
        if s.isdigit():
            return int(s)
        try:
            g = grp.getgrnam(s)
        except KeyError:
            self.parse_error("invalid group name: `{}`".format(s))
        return g.gr_gid

    def parse_host_port(self, s):
        try:
            return HostPort.parse(s)
        except ValueError as e:
            self.parse_error(e.msg)


class Unit:
    def __init__(self):
        pass

    def from_config(self, parser, key, val):
        pass


class Service:
    def __init__(self):
        self.syslog_identifier = None
        self.working_directory = None
        self.exec_start = []
        self.exec_start_pre = []
        self.exec_start_post = []
        self.exec_stop = []
        self.exec_stop_post = []
        self.kill_mode = "control-group"
        self.kill_signal = signal.SIGTERM
        self.send_sigkill = True
        self.timeout_stop_sec = 2
        self.user = os.getuid()
        self.group = os.getgid()

    def get_subprocess_kwargs(self, **kw):
        if self.working_directory is not None:
            kw["cwd"] = self.working_directory
        return kw

    def from_config(self, parser, key, val):
        if key == "SyslogIdentifier":
            self.syslog_identifier = val
        elif key == "WorkingDirectory":
            self.working_directory = val
        elif key == "ExecStart":
            self.exec_start.append(val)
        elif key == "ExecStartPre":
            self.exec_start_pre.append(val)
        elif key == "ExecStartPost":
            self.exec_start_post.append(val)
        elif key == "ExecStop":
            self.exec_stop.append(val)
        elif key == "ExecStopPost":
            self.exec_stop_post.append(val)
        elif key == "KillMode":
            self.kill_mode = val
        elif key == "KillSignal":
            self.kill_signal = parser.parse_signal(val)
        elif key == "SendSIGKILL":
            self.send_sigkill = parser.parse_bool(val)
        elif key == "TimeoutSec":
            self.timeout_stop_sec = parser.parse_delay(val)
        elif key == "TimeoutStopSec":
            self.timeout_stop_sec = parser.parse_delay(val)
        elif key == "User":
            self.user = parser.parse_user(val)
        elif key == "Group":
            self.group = parser.parse_group(val)

    def postprocess(self):
        if self.working_directory == "~":
            try:
                p = pwd.getpwuid(self.user)
            except KeyError:
                log.warn("cannot find passwd information for user id {}".format(self.user))
                self.working_directory = None
            self.working_directory = p.pw_dir

        if os.getuid() != 0 and os.getuid != self.user:
            log.warn("runnig as non-root: ignoring request to run as user {}".format(self.user))
        if os.getuid() != 0 and os.getgid != self.group:
            log.warn("runnig as non-root: ignoring request to run as group {}".format(self.group))

    @contextmanager
    def nonroot(self):
        """
        Context manager that runs code as non-root, using the user in this
        configuration.
        """
        changed_gid = False
        if os.getgid() == 0 and self.group != 0:
            os.setegid(self.group)
            changed_gid = True

        changed_uid = False
        if os.getuid() == 0 and self.user != 0:
            os.seteuid(self.user)
            changed_uid = True

        if changed_uid:
            try:
                user_info = pwd.getpwuid(self.user)
            except KeyError:
                user_info = None

            if user_info is not None:
                old_LOGNAME = os.environ.get("LOGNAME", None)
                old_USER = os.environ.get("USER", None)
                old_USERNAME = os.environ.get("USERNAME", None)
                old_HOME = os.environ.get("HOME", None)

                os.environ["LOGNAME"] = user_info.pw_name
                os.environ["USER"] = user_info.pw_name
                os.environ["USERNAME"] = user_info.pw_name
                os.environ["HOME"] = user_info.pw_dir

        yield

        if changed_uid and user_info is not None:
            os.environ["LOGNAME"] = old_LOGNAME
            os.environ["USER"] = old_USER
            os.environ["USERNAME"] = old_USERNAME
            os.environ["HOME"] = old_HOME

        if changed_uid:
            os.setuid(0)

        if changed_gid:
            os.setgid(0)


class Webrun:
    def __init__(self):
        self.display_number = 4
        self.display_geometry = "800x600"
        self._vnc_port = None
        self.web_port = HostPort(port=6080)
        self.log_file = None

    def from_config(self, parser, key, val):
        if key == "DisplayNumber":
            self.display_number = parser.parse_int(val)
        if key == "DisplayGeometry":
            self.display_geometry = val
        elif key == "VNCPort":
            self._vnc_port = parser.parse_host_port(val)
        elif key == "WebPort":
            self.web_port = parser.parse_host_port(val)
        elif key == "LogFile":
            self.log_file = val

    @property
    def vnc_port(self):
        if self._vnc_port is not None:
            return self._vnc_port
        return HostPort(port=self.display_number + 5900)

    @vnc_port.setter
    def vnc_port(self, value):
        self._vnc_port = value


class Config:
    def __init__(self):
        self.unit = Unit()
        self.service = Service()
        self.webrun = Webrun()

    def read_file(self, pathname):
        """
        Read a unit file from the given pathname, returning the parsed
        Config
        """
        with open(pathname, "rt") as fd:
            parser = Parser(fd)
            for section, key, val in parser.parse():
                section = section.lower()
                if section == "service":
                    self.service.from_config(parser, key, val)
                elif section == "unit":
                    self.unit.from_config(parser, key, val)
                elif section == "webrun":
                    self.webrun.from_config(parser, key, val)

        self.service.postprocess()
