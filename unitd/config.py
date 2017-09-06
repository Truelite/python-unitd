import re
import signal
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


class Webrun:
    def __init__(self):
        self.display_geometry = "800x600"
        self.web_port = 6080

    def from_config(self, parser, key, val):
        if key == "DisplayGeometry":
            self.display_geometry = val
        elif key == "WebPort":
            self.web_port = parser.parse_int(val)


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

