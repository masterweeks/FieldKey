#!/usr/bin/env python3
"""Make a strong password for a Postgres role and the SQL to set it, without the password
ever reaching the database in readable form.

Supabase logs every schema statement (log_statement = ddl), so
  alter role qgis_editor with password 'the-password';
would leave the password in the database logs. Instead this script hashes it on your
computer into Postgres's own SCRAM-SHA-256 format and prints
  alter role qgis_editor with password 'SCRAM-SHA-256$4096:...';
Postgres stores that hash as-is; only someone who knows the original password can log in.

Usage (run it yourself; don't paste the output into chats, tickets or files in the repo):
  python scripts/make_db_password.py                 # role qgis_editor, new random password
  python scripts/make_db_password.py --role qgis_editor
  python scripts/make_db_password.py --password-from-stdin   # hash a password you already have
"""
import argparse
import base64
import hashlib
import hmac
import secrets
import string
import sys

ITERATIONS = 4096   # Postgres's default scram_iterations


def scram_verifier(password: str, salt: bytes, iterations: int = ITERATIONS) -> str:
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"


def new_password(length: int = 32) -> str:
    # letters and digits only: nothing that needs escaping in QGIS, URLs or shells
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def self_test():
    # RFC 7677 test vector (password "pencil")
    v = scram_verifier("pencil", base64.b64decode("W22ZaJ0SNY7soEsUEjb6gQ=="), 4096)
    expected = ("SCRAM-SHA-256$4096:W22ZaJ0SNY7soEsUEjb6gQ==$"
                "WG5d8oPm3OtcPnkdi4Uo7BkeZkBFzpcXkuLmtbsT4qY=:wfPLwcE6nTWhTAmQ7tl2KeoiWGPlZqQxSrmfPwDl2dU=")
    if v != expected:
        sys.exit("self-test failed: SCRAM output doesn't match RFC 7677")


def check_password():
    """Does a password match the database's stored hash? Nothing is sent anywhere.
    Get the hash in the Supabase SQL Editor with:
      select rolpassword from pg_authid where rolname = 'qgis_editor';"""
    import getpass
    stored = input("Paste the stored hash (starts with SCRAM-SHA-256$): ").strip().strip("'\"")
    try:
        head, keys = stored.split("$", 1)[1].split("$", 1)
        iterations, salt = head.split(":", 1)
        verifier_now = scram_verifier("", base64.b64decode(salt), int(iterations))  # validates the format
    except Exception:
        sys.exit("That doesn't look like a SCRAM-SHA-256 hash.")
    pw = getpass.getpass("Type or paste the password (hidden): ")
    if pw != pw.strip():
        print("Note: the password has spaces at the start or end; QGIS would send those too.")
    ok = scram_verifier(pw, base64.b64decode(salt), int(iterations)) == stored
    print("MATCH: this password is the one the database expects." if ok
          else "NO MATCH: this isn't the password the database has. Make a new one and set it again.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--role", default="qgis_editor")
    ap.add_argument("--password-from-stdin", action="store_true", help="hash a password read from stdin instead of making one")
    ap.add_argument("--self-test", action="store_true", help="check the hashing against the RFC 7677 test vector and exit")
    ap.add_argument("--check", action="store_true", help="check a password against the hash stored in the database")
    a = ap.parse_args()
    self_test()
    if a.self_test:
        print("self-test passed")
        return
    if a.check:
        check_password()
        return
    if not all(ch.isalnum() or ch == "_" for ch in a.role):
        sys.exit("role name must be letters, digits or _")
    pw = sys.stdin.readline().rstrip("\r\n") if a.password_from_stdin else new_password()
    if len(pw) < 16:
        sys.exit("use at least 16 characters")
    sql = f"alter role {a.role} with password '{scram_verifier(pw, secrets.token_bytes(16))}';"
    print("1) Save this password in your password manager now (it is not stored anywhere else):\n")
    if not a.password_from_stdin:
        print("   " + pw + "\n")
    else:
        print("   (the password you typed)\n")
    print("2) Run this in the Supabase SQL Editor. It holds only a one-way hash, so it's safe in logs:\n")
    print("   " + sql + "\n")


if __name__ == "__main__":
    main()
