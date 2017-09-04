import re

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
