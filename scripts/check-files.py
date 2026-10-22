"""Fast checks on the file list supplied by pre-commit; never changes files."""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import yaml


def check(path):
    data = path.read_bytes()
    # The original school guide is UTF-16. Scan its contents too, without
    # changing historical documentation or skipping its secret/conflict checks.
    text = data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    if re.search(r"^(?:<{7} |={7}$|>{7} )", text, re.MULTILINE):
        raise ValueError("unresolved merge conflict")
    if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", text):
        raise ValueError("private key must not be committed")
    if path.suffix.lower() in (".yaml", ".yml"):
        list(yaml.safe_load_all(text))
    if path.suffix.lower() == ".xml":
        ET.fromstring(text)


if __name__ == "__main__":
    failed = False
    for name in sys.argv[1:]:
        path = Path(name)
        if not path.is_file():
            continue
        try:
            check(path)
        except (ValueError, UnicodeError, yaml.YAMLError, ET.ParseError) as error:
            # A parser error may echo source text, so do not print its contents.
            print(f"FAIL {path}: {type(error).__name__}; check syntax, merge markers and private keys")
            failed = True
    sys.exit(1 if failed else 0)
