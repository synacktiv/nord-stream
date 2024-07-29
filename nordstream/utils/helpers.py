def isHexadecimal(s):
    hex_digits = set("0123456789abcdefABCDEF")
    return all(c in hex_digits for c in s)


def isGitLabSessionCookie(s):
    return isHexadecimal(s) and len(s) == 32
