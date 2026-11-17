"""Composition *plans*. Historical renderers/verifiers are not recovered here."""
from . import bigo, bugfixing, codeclone, verus

DOMAINS = {"bugfixing": bugfixing, "verus": verus, "bigo": bigo, "codeclone": codeclone}
