import logging

_LOGGER: logging.Logger = logging.getLogger(__package__)


def human_bytes(B):
    """Return the given bytes as a human friendly KB, MB, GB, or TB string"""
    # https://stackoverflow.com/questions/12523586/python-format-size-application-converting-b-to-kb-mb-gb-tb/63839503
    B = float(B)
    KB = float(1024)
    MB = float(KB**2)  # 1,048,576
    GB = float(KB**3)  # 1,073,741,824
    TB = float(KB**4)  # 1,099,511,627,776

    if B < KB:
        return "{0} {1}".format(B, "Bytes" if 0 == B > 1 else "Byte")
    elif KB <= B < MB:
        return "{0:.2f} KB".format(B / KB)
    elif MB <= B < GB:
        return "{0:.2f} MB".format(B / MB)
    elif GB <= B < TB:
        return "{0:.2f} GB".format(B / GB)
    elif TB <= B:
        return "{0:.2f} TB".format(B / TB)


def parse_human_string(traffic: str) -> int:
    """Returns the number of bytes in the human string. Example input: 12.2 GB"""
    try:
        parts = traffic.split(" ")
        value = float(parts[0])
        unit = parts[1]

        KB = float(1024)
        MB = float(KB**2)  # 1,048,576
        GB = float(KB**3)  # 1,073,741,824
        TB = float(KB**4)  # 1,099,511,627,776

        b = 0
        if unit == "KB":
            b = value * KB
        if unit == "MB":
            b = value * MB
        if unit == "GB":
            b = value * GB
        if unit == "TB":
            b = value * TB

        return int(b)
    except Exception as exception:
        _LOGGER.debug("Failed to parse %s", traffic, exc_info=exception)
        pass

    return 0


def safe_cast(val, to_type, default=None):
    try:
        return to_type(val)
    except (ValueError, TypeError):
        return default
