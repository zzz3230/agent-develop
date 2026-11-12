def parse_port(text):
    """Return the port number 1..65535 written in text; raise ValueError otherwise."""
    value = int(text)
    if value < 1 or value > 65536:
        raise ValueError(text)
    return value
