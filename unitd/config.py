import re
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

def parse(fd):
    current_section = None

    for lineno, line in enumerate(fd, start=1):
        if re_empty.match(line): continue

        mo = re_section.match(line)
        if mo:
            current_section = mo.group("section")
            continue

        mo = re_assign.match(line)
        if mo:
            if current_section is None:
                raise ParseError(fd, lineno, "key=value line found outside all sections")
            yield current_section, mo.group("key"), mo.group("val")
            continue

        raise ParseError(fd, lineno, "line not recognised as comment, [section] or assignment")


class Unit:
    def __init__(self):
        pass

    def from_config(self, key, val):
        pass


class Service:
    def __init__(self):
        self.syslog_identifier = None
        self.working_directory = None
        self.exec_start = []
        self.exec_start_pre = []
        self.exec_start_post = []

    def get_subprocess_kwargs(self, **kw):
        if self.working_directory is not None:
            kw["cwd"] = self.working_directory
        return kw

    def from_config(self, key, val):
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


class Config:
    def __init__(self):
        self.unit = Unit()
        self.service = Service()

    @classmethod
    def read_file(cls, pathname):
        """
        Read a unit file from the given pathname, returning the parsed
        Config
        """
        res = cls()

        with open(pathname, "rt") as fd:
            for section, key, val in parse(fd):
                section = section.lower()
                if section == "service":
                    res.service.from_config(key, val)
                elif section == "unit":
                    res.unit.from_config(key, val)

        return res
